#!/usr/bin/env python3
"""Voll-automatisches Daten-Update: Scrape -> Anreicherung -> Ratings -> DB -> Upload.

Kette (jede Stufe nur bei Erfolg der vorherigen):
  1. collect_all/collect_seasons-Logik: neue Spiel-IDs der laufenden Bewerbe
  2. oefb_scraper (nur neue IDs) -> data_inc/
  3. player_ages (nur neue IDs, Profil-Cache) -> data_inc/players_new.csv
  4. merge_data: an data/ anhaengen
  5. fix_events: fehlende Tor-Minuten nachladen
  6. plusminus: ratings.csv neu
  7. build_extras + build_db: player_extras.json + oefb.sqlite
  8. build_dashboard: scout.json/matches_index.json (gz) + dash_profile in oefb.sqlite
  9. Upload zum Server (ADMIN_TOKEN): oefb.sqlite, scout.json.gz, matches_index.json.gz

Konfiguration via .env (nicht committen): SERVER_URL, ADMIN_TOKEN.
Aufruf: python3 update_all.py [--skip-upload] [--bewerbe ID ...]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def env_from_dotenv() -> dict:
    env = dict(os.environ)
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


def run(label: str, args: list[str]) -> None:
    print(f"\n=== {label} ===", flush=True)
    rc = subprocess.run([PY] + args, cwd=ROOT).returncode
    if rc != 0:
        sys.exit(f"ABBRUCH: {label} endete mit Exit {rc}")




def upload(env: dict) -> None:
    url, tok = env.get("SERVER_URL", "").rstrip("/"), env.get("ADMIN_TOKEN", "")
    if not url or not tok:
        sys.exit("SERVER_URL/ADMIN_TOKEN fehlen (.env) — Upload nicht möglich.")
    # Reihenfolge: erst DB (Profile), dann die Startdateien des Dashboards
    files = ["oefb.sqlite", "scout.json.gz", "matches_index.json.gz"]
    for name in files:
        p = os.path.join(ROOT, "data", name)
        if not os.path.exists(p):
            print(f"  (fehlt, übersprungen: {name})"); continue
        print(f"  Upload {name} ({os.path.getsize(p)/1e6:.1f} MB) …", flush=True)
        rc = subprocess.run(["curl", "-sf", "-X", "POST",
                             f"{url}/admin/upload?name={name}",
                             "-H", f"authorization: Bearer {tok}",
                             "--data-binary", f"@{p}"],
                            capture_output=True, text=True)
        if rc.returncode != 0:
            sys.exit(f"Upload {name} fehlgeschlagen: {rc.stderr[:300]}")
        print("   ", rc.stdout[:160])
    print("Upload komplett.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-upload", action="store_true")
    ap.add_argument("--skip-scrape", action="store_true",
                    help="nur DB bauen + hochladen (Daten unveraendert)")
    args = ap.parse_args()
    env = env_from_dotenv()
    os.environ.update({k: env[k] for k in ("SERVER_URL", "ADMIN_TOKEN") if k in env})

    if not args.skip_scrape:
        # all_ids.txt ist die historische Gesamtliste; collect_all schreibt nur die
        # laufenden Bewerbe -> danach wieder vereinigen (alte zuerst, neue hinten).
        old_ids = [l.strip() for l in open("data/all_ids.txt", encoding="utf-8")
                   if l.strip()] if os.path.exists("data/all_ids.txt") else []
        run("IDs sammeln (laufende Bewerbe)", ["collect_all.py", "-o", "data/all_ids.txt"])
        cur_ids = [l.strip() for l in open("data/all_ids.txt", encoding="utf-8") if l.strip()]
        seen = set(old_ids)
        with open("data/all_ids.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(old_ids + [i for i in cur_ids if not (i in seen or seen.add(i))]) + "\n")
        # neue IDs = laufende Bewerbe minus bereits vorhandene matches
        import csv as _csv
        have = {r["match_id"] for r in _csv.DictReader(open("data/matches.csv", encoding="utf-8"))}
        new = [i for i in cur_ids if i not in have]
        print(f"Neue Spiele: {len(new)}")
        if new:
            os.makedirs("data_inc", exist_ok=True)
            open("data_inc/new_ids.txt", "w").write("\n".join(new) + "\n")
            run("Scrape (neu)", ["oefb_scraper.py", "--ids-file", "data_inc/new_ids.txt",
                                 "--delay", "0.6", "--out-dir", "data_inc", "--format", "both"])
            run("Anreicherung (neu)", ["player_ages.py", "--ids-file", "data_inc/new_ids.txt",
                                       "-o", "data_inc/players_new.csv",
                                       "--cache", "data/profiles_cache.json",
                                       "--profiles-json", "data_inc/profiles_new.json",
                                       "--delay", "0.35"])
            run("Merge", ["merge_data.py", "--base", "data", "--inc", "data_inc",
                          "--players-new", "data_inc/players_new.csv"])
            run("Event-Reparatur", ["fix_events.py", "--delay", "0.55"])
            run("Ratings", ["plusminus.py", "-o", "data/ratings.csv"])
        else:
            print("Keine neuen Spiele — überspringe Scrape-Stufen.")

    run("Extras", ["build_extras.py"])
    run("SQLite-DB", ["build_db.py"])
    run("Dashboard-Daten", ["build_dashboard.py"])     # schreibt scout.json(.gz) etc. selbst
    if not args.skip_upload:
        upload(env)
    print("\nFERTIG.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
