#!/usr/bin/env python3
"""Fuegt einen inkrementell gescrapten Teil-Datensatz (nur neue Spiele) an den
bestehenden Datensatz an – dedupliziert nach match_id.

- matches.json          : Vereinigung (dict nach match_id)
- matches/events/lineups.csv : neue Zeilen anhaengen (nur neue match_ids)
- players.csv           : players_new.csv anhaengen (nur neue match_ids)
- players_profiles.json : aus profiles_cache.json neu erzeugen fuer alle
                          player_ids der zusammengefuehrten players.csv

Aufruf:
    python merge_data.py --base data --inc data_inc --players-new data_inc/players_new.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

csv.field_size_limit(10_000_000)


def log(*a):
    print(*a, file=sys.stderr)


def merge_matches_json(base_p: str, inc_p: str) -> int:
    base = json.load(open(base_p, encoding="utf-8")) if os.path.exists(base_p) else []
    inc = json.load(open(inc_p, encoding="utf-8")) if os.path.exists(inc_p) else []
    by = {str(m.get("match_id")): m for m in base}
    added = 0
    for m in inc:
        mid = str(m.get("match_id"))
        if mid not in by:
            by[mid] = m; added += 1
    out = list(by.values())
    json.dump(out, open(base_p, "w", encoding="utf-8"), ensure_ascii=False)
    log(f"  matches.json: {len(base)} + {added} neu = {len(out)}")
    return added


def append_csv(base_p: str, inc_p: str, key: str = "match_id") -> None:
    """Haengt Zeilen aus inc an base an, deren key-Wert noch nicht in base steht."""
    if not os.path.exists(inc_p):
        log(f"  {inc_p}: fehlt – uebersprungen"); return
    with open(base_p, encoding="utf-8") as f:
        base_rows = list(csv.reader(f))
    base_head = base_rows[0]
    existing_keys = set()
    ki = base_head.index(key)
    for r in base_rows[1:]:
        if len(r) > ki:
            existing_keys.add(r[ki])
    with open(inc_p, encoding="utf-8") as f:
        inc_rows = list(csv.reader(f))
    inc_head = inc_rows[0]
    if inc_head != base_head:
        raise SystemExit(f"Spalten stimmen nicht ueberein in {os.path.basename(base_p)}:\n"
                         f"  base={base_head}\n  inc ={inc_head}")
    kj = inc_head.index(key)
    new = [r for r in inc_rows[1:] if len(r) > kj and r[kj] not in existing_keys]
    with open(base_p, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerows(new)
    log(f"  {os.path.basename(base_p)}: +{len(new)} Zeilen (von {len(inc_rows)-1})")


def regen_profiles(players_csv: str, cache_p: str, out_p: str) -> None:
    cache = json.load(open(cache_p, encoding="utf-8")) if os.path.exists(cache_p) else {}
    pids = set()
    with open(players_csv, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pid = row.get("player_id")
            if pid:
                pids.add(pid)
    profiles = {pid: cache[pid] for pid in sorted(pids) if cache.get(pid)}
    json.dump(profiles, open(out_p, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    log(f"  players_profiles.json: {len(profiles)} Spieler (aus Cache {len(cache)})")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", default="data")
    p.add_argument("--inc", default="data_inc")
    p.add_argument("--players-new", default="data_inc/players_new.csv")
    p.add_argument("--cache", default="data/profiles_cache.json")
    args = p.parse_args(argv)

    log("== merge_data ==")
    merge_matches_json(f"{args.base}/matches.json", f"{args.inc}/matches.json")
    for name in ("matches.csv", "events.csv", "lineups.csv"):
        append_csv(f"{args.base}/{name}", f"{args.inc}/{name}")
    append_csv(f"{args.base}/players.csv", args.players_new)
    regen_profiles(f"{args.base}/players.csv", args.cache,
                   f"{args.base}/players_profiles.json")

    # Kontrolle
    with open(f"{args.base}/players.csv", encoding="utf-8") as f:
        n = sum(1 for _ in f) - 1
    log(f"== fertig: players.csv {n} Zeilen ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
