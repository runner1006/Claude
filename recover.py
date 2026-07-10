#!/usr/bin/env python3
"""Nachhol-Lauf fuer Spiele, die beim inkrementellen Enrich wegen einer
voruebergehenden Server-Blockade keine Aufstellungsdaten bekamen.

Ruft player_ages iterativ auf der jeweils noch fehlenden ID-Menge auf, bis alle
Spiele Spieler-Zeilen haben oder keine Fortschritte mehr moeglich sind. Sammelt
alle gewonnenen Zeilen in einer Ausgabedatei.

Aufruf:
    python recover.py --missing data_inc/missing_ids.txt \
        --out data_inc/players_recover.csv --cache data/profiles_cache.json
"""
from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys

csv.field_size_limit(10_000_000)


def mids(path):
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {r["match_id"] for r in csv.DictReader(f)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--missing", default="data_inc/missing_ids.txt")
    p.add_argument("--out", default="data_inc/players_recover.csv")
    p.add_argument("--cache", default="data/profiles_cache.json")
    p.add_argument("--delay", type=float, default=0.5)
    p.add_argument("--max-iter", type=int, default=6)
    args = p.parse_args(argv)

    remaining = [l.strip() for l in open(args.missing, encoding="utf-8") if l.strip()]
    tmp_ids = "data_inc/_rec_remaining.txt"
    tmp_out = "data_inc/_rec_iter.csv"
    header = None
    accum_rows: list[dict] = []
    accum_mids: set[str] = set()

    for it in range(1, args.max_iter + 1):
        if not remaining:
            break
        with open(tmp_ids, "w", encoding="utf-8") as f:
            f.write("\n".join(remaining) + "\n")
        print(f"\n=== Iteration {it}: {len(remaining)} Spiele offen ===", flush=True)
        rc = subprocess.run([
            sys.executable, "player_ages.py", "--ids-file", tmp_ids,
            "-o", tmp_out, "--cache", args.cache,
            "--profiles-json", "data_inc/_rec_prof.json", "--delay", str(args.delay),
        ]).returncode
        if rc != 0:
            print(f"  player_ages Exit {rc} – breche ab", flush=True)
            break
        done = mids(tmp_out)
        # neue Zeilen dieser Iteration einsammeln
        with open(tmp_out, encoding="utf-8") as f:
            rd = csv.DictReader(f)
            header = rd.fieldnames
            for row in rd:
                if row["match_id"] not in accum_mids or True:  # alle Zeilen der neu erledigten
                    accum_rows.append(row)
        accum_mids |= done
        before = len(remaining)
        remaining = [m for m in remaining if m not in done]
        print(f"  erledigt: {len(done)} | noch offen: {len(remaining)} "
              f"(Fortschritt {before-len(remaining)})", flush=True)
        if before == len(remaining):
            print("  kein Fortschritt mehr – Stopp", flush=True)
            break

    # Ausgabe schreiben
    if header:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            w.writerows(accum_rows)
    print(f"\nFERTIG: {len(accum_mids)} Spiele nachgeholt, {len(accum_rows)} Zeilen "
          f"-> {args.out}. Noch offen: {len(remaining)}", flush=True)
    if remaining:
        open("data_inc/still_missing.txt", "w").write("\n".join(remaining) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
