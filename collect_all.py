#!/usr/bin/env python3
"""Sammelt die Spiel-IDs der vollen Saison aller aktuell enthaltenen Bewerbe
und schreibt sie dedupliziert nach data/all_ids.txt.

Alle verfuegbaren Runden je Bewerb (rounds=None -> collect_ids nimmt automatisch
alle). Aufruf: python collect_all.py [--delay 0.6]
"""
from __future__ import annotations

import argparse
import sys

import collect_ids as ci

# Bewerb-ID -> Anzeigename (die 7 aktuell enthaltenen Ligen der Saison 2025/26)
BEWERBE = [
    ("226374", "Regionalliga Mitte"),
    ("226282", "Landesliga Steiermark"),
    ("226273", "Oberliga Nord"),
    ("226278", "Oberliga Mitte West"),
    ("226272", "Oberliga Süd Ost"),
    ("227230", "ÖFB Jugendliga U18"),
    ("227253", "ÖFB Jugendregionalliga U18"),
]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-o", "--out", default="data/all_ids.txt")
    p.add_argument("--delay", type=float, default=0.6,
                   help="Pause zwischen Runden-Abfragen (Default: 0.6)")
    args = p.parse_args(argv)

    session = ci.make_session()
    seen: set[str] = set()
    ordered: list[str] = []
    for bid, name in BEWERBE:
        ids = ci.collect(session, bid, None, args.delay)  # None = alle Runden
        new = [i for i in ids if not (i in seen or seen.add(i))]
        ordered.extend(new)
        print(f"== {name} ({bid}): {len(ids)} IDs, {len(new)} neu "
              f"(gesamt {len(ordered)})", file=sys.stderr)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(ordered) + ("\n" if ordered else ""))
    print(f"\nFERTIG: {len(ordered)} eindeutige Spiel-IDs -> {args.out}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
