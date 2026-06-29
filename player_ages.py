#!/usr/bin/env python3
"""
OEFB Spieler-Alter
==================

Ermittelt fuer jedes Spiel alle eingesetzten/gelisteten Spieler samt Alter
und schreibt sie als CSV (eine Zeile pro Spieler/Spiel).

Datenquellen
------------
1. Spielbericht (NICHT die Druckansicht):
       https://www.oefb.at/bewerbe/Spiel/Spielbericht/<SPIEL_ID>/
   enthaelt ein strukturiertes JSON (appPreloads) mit den Aufstellungen
   `heimAufstellung`/`gastAufstellung` – pro Spieler u.a. `rueckennummer`,
   `name`, `kapitaen` und `url` (-> /Profile/Spieler/<SPIELER_ID>).
2. Spielerprofil:
       https://www.oefb.at/Profile/Spieler/<SPIELER_ID>
   enthaelt `"geburtsdatum": <ms>` (Unix-Timestamp, lokale Mitternacht).

WICHTIG: Die oeffentlichen Profile geben aus Datenschutzgruenden nur das
GEBURTSJAHR preis (intern als 1. Januar gespeichert), nicht den genauen Tag.
Das Alter ist daher jahresbasiert und auf +-1 Jahr genau (Spalte `age` =
Stichtagsjahr - Geburtsjahr).

Die Anubis-Bot-Schutz-Challenge wird automatisch geloest (via oefb_scraper).
Geburtsdaten werden in einer Cache-Datei zwischengespeichert, damit Profile
ueber mehrere Laeufe hinweg nicht erneut geladen werden.

Beispiele
---------
    python player_ages.py --ids 3839515 -o players.csv
    python player_ages.py --ids-file rlm_ids.txt -o players.csv --delay 1.5
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import time

import requests

import oefb_scraper as oefb

REPORT_URL = "https://www.oefb.at/bewerbe/Spiel/Spielbericht/{id}/"
PROFILE_URL = "https://www.oefb.at/Profile/Spieler/{id}"

# Positionsgruppen in der Aufstellung; `ersatz` = Bank, alles andere = Startelf.
_GROUPS = ("tor", "abwehr", "mittelfeld", "sturm", "weitere", "ersatz")
_PROFILE_ID_RE = re.compile(r"/Profile/Spieler/(\d+)")
_GEBURT_RE = re.compile(r'"geburtsdatum"\s*:\s*(\d+)')

log = oefb.log


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(oefb.DEFAULT_HEADERS)
    return s


def get(session: requests.Session, url: str, timeout: float = 30.0) -> str:
    """GET mit automatischer Anubis-Loesung (Cookie bleibt in der Session)."""
    r = session.get(url, timeout=timeout)
    r.raise_for_status()
    oefb._apply_encoding(r)
    if oefb._detect_challenge(r.text):
        return oefb.solve_challenge(session, url, r.text, timeout)
    return r.text


def _find_match_data(html: str) -> dict | None:
    """Holt das appPreloads-Objekt mit den Aufstellungen aus der Spielberichtseite."""
    dec = json.JSONDecoder()
    for m in re.finditer(r"appPreloads\['?-?\d+'?\]\s*=\s*", html):
        start = html.find("[", m.end())
        if start == -1:
            continue
        try:
            arr, _ = dec.raw_decode(html, start)
        except ValueError:
            continue
        for item in arr:
            if isinstance(item, dict) and "heimAufstellung" in item:
                return item
    return None


def _players_from_lineup(auf: dict, side: str) -> list[dict]:
    """Flacht eine Aufstellung (`heim`/`gast`) zu Spieler-Dicts ab."""
    out: list[dict] = []
    team = auf.get("vereinName")
    for group in _GROUPS:
        for p in auf.get(group) or []:
            pid = _PROFILE_ID_RE.search(p.get("url") or "")
            out.append({
                "side": side,
                "team": team,
                "role": "bench" if group == "ersatz" else "starter",
                "position": group,
                "number": p.get("rueckennummer"),
                "name": p.get("name"),
                "player_id": pid.group(1) if pid else None,
                "captain": bool(p.get("kapitaen")),
                "goals": p.get("tore") or 0,
            })
    return out


def match_players(session: requests.Session, match_id: str,
                  timeout: float = 30.0) -> tuple[str, list[dict]]:
    """Liefert (titel, spielerliste) fuer ein Spiel."""
    html = get(session, REPORT_URL.format(id=match_id), timeout)
    data = _find_match_data(html)
    if not data:
        raise RuntimeError(f"Keine Aufstellungsdaten fuer Spiel {match_id} gefunden.")
    players = (_players_from_lineup(data.get("heimAufstellung") or {}, "home") +
               _players_from_lineup(data.get("gastAufstellung") or {}, "away"))
    return data.get("title", str(match_id)), players


def birthdate_of(session: requests.Session, player_id: str,
                 cache: dict, timeout: float = 30.0, delay: float = 0.0) -> str | None:
    """ISO-Geburtsdatum eines Spielers (mit Cache). None wenn nicht gefunden."""
    if player_id in cache:
        return cache[player_id]
    html = get(session, PROFILE_URL.format(id=player_id), timeout)
    m = _GEBURT_RE.search(html)
    iso = None
    if m:
        # Timestamp ist lokale Mitternacht (Europe/Vienna); +12h-Offset, damit
        # die Datums-Umrechnung TZ-unabhaengig auf den richtigen Tag faellt.
        secs = int(m.group(1)) / 1000 + 12 * 3600
        iso = dt.datetime.utcfromtimestamp(secs).date().isoformat()
    cache[player_id] = iso
    if delay > 0:
        time.sleep(delay)
    return iso


def age_on(birthdate_iso: str | None, ref: dt.date) -> int | None:
    if not birthdate_iso:
        return None
    b = dt.date.fromisoformat(birthdate_iso)
    return ref.year - b.year - ((ref.month, ref.day) < (b.month, b.day))


def load_cache(path: str | None) -> dict:
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def save_cache(path: str | None, cache: dict) -> None:
    if not path:
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=0)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Ermittelt das Alter jedes Spielers pro Spiel.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    src = p.add_argument_group("Spiel-IDs")
    src.add_argument("--ids", nargs="+", metavar="ID", help="Einzelne Spiel-IDs")
    src.add_argument("--ids-file", metavar="DATEI", help="Datei mit einer ID pro Zeile")
    p.add_argument("-o", "--out", default="players.csv", help="Ziel-CSV (Default: players.csv)")
    p.add_argument("--cache", default="players_cache.json",
                   help="Cache-Datei fuer Geburtsdaten (Default: players_cache.json)")
    p.add_argument("--ref-date", metavar="YYYY-MM-DD",
                   help="Stichtag fuer die Altersberechnung (Default: heute)")
    p.add_argument("--delay", type=float, default=0.5,
                   help="Pause zwischen Profil-Abfragen in Sek. (Default: 0.5)")
    p.add_argument("--timeout", type=float, default=30.0)
    args = p.parse_args(argv)

    oefb.logging.basicConfig(level=oefb.logging.INFO,
                             format="%(asctime)s %(levelname)s %(message)s",
                             datefmt="%H:%M:%S")

    ids: list[str] = list(args.ids or [])
    if args.ids_file:
        ids += [l.strip() for l in open(args.ids_file, encoding="utf-8")
                if l.strip() and not l.startswith("#")]
    ids = list(dict.fromkeys(ids))
    if not ids:
        p.error("Keine IDs (--ids oder --ids-file).")

    ref = dt.date.fromisoformat(args.ref_date) if args.ref_date else dt.date.today()
    session = make_session()
    cache = load_cache(args.cache)
    log.info("%d Spiel(e), Stichtag %s, %d Geburtsdaten im Cache.",
             len(ids), ref.isoformat(), len(cache))

    rows: list[dict] = []
    for idx, mid in enumerate(ids, 1):
        try:
            title, players = match_players(session, mid, args.timeout)
        except Exception as exc:  # noqa: BLE001
            log.error("[%d/%d] Spiel %s: %s", idx, len(ids), mid, exc)
            continue
        for pl in players:
            iso = None
            if pl["player_id"]:
                try:
                    iso = birthdate_of(session, pl["player_id"], cache,
                                       args.timeout, args.delay)
                except Exception as exc:  # noqa: BLE001
                    log.warning("  Profil %s fehlgeschlagen: %s", pl["player_id"], exc)
            pl["match_id"] = str(mid)
            # oeffentlich ist nur das Jahr bekannt (Datum = 1.1.) -> nur Jahr ausgeben
            pl["birth_year"] = int(iso[:4]) if iso else None
            pl["age"] = age_on(iso, ref)
            rows.append(pl)
        ages = [r["age"] for r in rows if r["match_id"] == str(mid) and r["age"] is not None]
        avg = f"{sum(ages)/len(ages):.1f}" if ages else "—"
        log.info("[%d/%d] %s: %d Spieler, Ø %s J.", idx, len(ids), title, len(players), avg)
        save_cache(args.cache, cache)  # inkrementell sichern

    fields = ["match_id", "side", "team", "role", "position", "number", "name",
              "player_id", "birth_year", "age", "captain", "goals"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})
    log.info("Fertig. %d Spieler-Zeilen -> %s (Cache: %d Geburtsdaten)",
             len(rows), args.out, len(cache))
    return 0


if __name__ == "__main__":
    sys.exit(main())
