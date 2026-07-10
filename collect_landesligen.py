#!/usr/bin/env python3
"""Sammelt die Spiel-IDs der 9 Landesligen (Top-Liga je Bundesland) + der 3
Regionalligen fuer die letzten 3 Saisonen. Schreibt die NEUEN IDs (die noch
nicht in all_ids.txt stehen) nach data/new_ids2.txt und mergt sie zugleich in
data/all_ids.txt.

Aufruf: python collect_landesligen.py [--delay 0.5]
"""
from __future__ import annotations

import argparse
import sys

import collect_ids as ci

# (Bewerb-ID, Label) — 26 Landesliga- + 6 Regionalliga-Bewerbe (ohne die bereits
# vorhandene Landesliga Steiermark 2025/26 = 226282).
NEW = [
    # --- Landesligen (Top-Liga je Bundesland), je 3 Saisonen ---
    ("226635", "Wien Stadtliga 25/26"), ("221791", "Wien Stadtliga 24/25"), ("216455", "Wien Stadtliga 23/24"),
    ("226514", "NÖ 1. Landesliga 25/26"), ("221652", "NÖ 1. Landesliga 24/25"), ("216029", "NÖ 1. Landesliga 23/24"),
    ("226443", "Bgld Landesliga 25/26"), ("221814", "Bgld Landesliga 24/25"), ("215968", "Bgld Landesliga 23/24"),
    ("226368", "OÖ Liga 25/26"), ("221366", "OÖ Liga 24/25"), ("216120", "OÖ Liga 23/24"),
    ("221195", "Stmk Landesliga 24/25"), ("215889", "Stmk Landesliga 23/24"),  # 25/26 vorhanden
    ("226828", "Ktn Liga 25/26"), ("221445", "Ktn Liga 24/25"), ("216539", "Ktn Liga 23/24"),
    ("226782", "Sbg Liga 25/26"), ("221330", "Sbg Liga 24/25"), ("216145", "Sbg Liga 23/24"),
    ("226427", "Tirol Liga 25/26"), ("221488", "Tirol Liga 24/25"), ("216605", "Tirol Liga 23/24"),
    ("226852", "Vbg Eliteliga 25/26"), ("221671", "Vbg Eliteliga 24/25"), ("216578", "Vbg Eliteliga 23/24"),
    # --- Regionalligen 24/25 + 23/24 (25/26 vorhanden) ---
    ("221198", "RL Mitte 24/25"), ("216540", "RL Mitte 23/24"),
    ("221700", "RL Ost 24/25"), ("216879", "RL Ost 23/24"),
    ("221326", "RL West 24/25"), ("216990", "RL West 23/24"),
]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--all-ids", default="data/all_ids.txt")
    p.add_argument("--new-out", default="data/new_ids2.txt")
    p.add_argument("--delay", type=float, default=0.5)
    args = p.parse_args(argv)

    existing: list[str] = []
    seen: set[str] = set()
    try:
        for line in open(args.all_ids, encoding="utf-8"):
            i = line.strip()
            if i and not i.startswith("#") and i not in seen:
                seen.add(i); existing.append(i)
    except FileNotFoundError:
        pass
    print(f"Bestehend: {len(existing)} IDs", file=sys.stderr)

    session = ci.make_session()
    new_ids: list[str] = []
    for bid, name in NEW:
        try:
            ids = ci.collect(session, bid, None, args.delay)
        except Exception as exc:  # noqa: BLE001
            print(f"!! {name} ({bid}): FEHLER {exc}", file=sys.stderr); continue
        fresh = [i for i in ids if not (i in seen or seen.add(i))]
        new_ids.extend(fresh)
        print(f"== {name} ({bid}): {len(ids)} IDs, {len(fresh)} neu", file=sys.stderr)

    # Nur-neue-IDs (fuer inkrementelles Scrapen)
    with open(args.new_out, "w", encoding="utf-8") as f:
        f.write("\n".join(new_ids) + ("\n" if new_ids else ""))
    # Gesamtliste aktualisieren
    allids = existing + new_ids
    with open(args.all_ids, "w", encoding="utf-8") as f:
        f.write("\n".join(allids) + ("\n" if allids else ""))
    print(f"\nFERTIG: {len(new_ids)} NEUE IDs -> {args.new_out}; "
          f"gesamt {len(allids)} -> {args.all_ids}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
