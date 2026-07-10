#!/usr/bin/env python3
"""Sammelt die Spiel-IDs zusaetzlicher Bewerbe/Saisonen (U16/U15 + Vorsaisonen
U18/JRL + Regionalliga Ost/West 2025/26) und MERGT sie dedupliziert in
data/all_ids.txt (bestehende IDs bleiben erhalten).

Aufruf: python collect_seasons.py [--delay 0.5]
"""
from __future__ import annotations

import argparse
import sys

import collect_ids as ci

# (Bewerb-ID, Anzeigename)  – die 15 neu hinzuzufuegenden Bewerbe/Saisonen.
NEW = [
    ("222101", "Jugendliga U18 2024/25"),
    ("217011", "Jugendliga U18 2023/24"),
    ("227229", "Jugendliga U16 2025/26"),
    ("222100", "Jugendliga U16 2024/25"),
    ("217009", "Jugendliga U16 2023/24"),
    ("227228", "Jugendliga U15 2025/26"),
    ("222099", "Jugendliga U15 2024/25"),
    ("217008", "Jugendliga U15 2023/24"),
    ("222103", "Jugendregionalliga U18 2024/25"),
    ("217020", "Jugendregionalliga U18 2023/24"),
    ("227252", "Jugendregionalliga U16 2025/26"),
    ("222102", "Jugendregionalliga U16 2024/25"),
    ("217021", "Jugendregionalliga U16 2023/24"),
    ("226510", "Regionalliga Ost 2025/26"),
    ("226774", "Regionalliga West 2025/26"),
]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-o", "--out", default="data/all_ids.txt")
    p.add_argument("--delay", type=float, default=0.5)
    args = p.parse_args(argv)

    # Bestehende IDs laden (Reihenfolge + Dedup erhalten)
    existing: list[str] = []
    seen: set[str] = set()
    try:
        for line in open(args.out, encoding="utf-8"):
            i = line.strip()
            if i and not i.startswith("#") and i not in seen:
                seen.add(i)
                existing.append(i)
    except FileNotFoundError:
        pass
    print(f"Bestehend in {args.out}: {len(existing)} IDs", file=sys.stderr)

    session = ci.make_session()
    added_total = 0
    added: list[str] = []
    for bid, name in NEW:
        ids = ci.collect(session, bid, None, args.delay)  # alle Runden
        new = [i for i in ids if not (i in seen or seen.add(i))]
        added.extend(new)
        added_total += len(new)
        print(f"== {name} ({bid}): {len(ids)} IDs, {len(new)} neu", file=sys.stderr)

    allids = existing + added
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(allids) + ("\n" if allids else ""))
    print(f"\nFERTIG: +{added_total} neue IDs -> {args.out} "
          f"(gesamt {len(allids)})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
