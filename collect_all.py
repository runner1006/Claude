#!/usr/bin/env python3
"""Sammelt die Spiel-IDs der vollen Saison aller aktuell enthaltenen Bewerbe (2026/27)
und schreibt sie dedupliziert nach data/all_ids.txt.

Alle verfuegbaren Runden je Bewerb (rounds=None -> collect_ids nimmt automatisch
alle). Aufruf: python collect_all.py [--delay 0.6]
"""
from __future__ import annotations

import argparse
import sys

import collect_ids as ci

# Bewerb-ID -> Anzeigename (die aktuell enthaltenen Ligen der Saison 2026/27).
# IDs aufgeloest ueber die "saisonen"-Liste der Vorjahres-Bewerbsseiten (Stand 02.11.2026).
# Reform 2026/27: Regionalliga Mitte -> Regionalliga Nord; neu Regionalliga Sued
# (Stmk/Ktn, je 14 Runden); HYPO Tirol Liga -> 1. HYPO TIROL Landesliga Ost.
BEWERBE = [
    # Regionalligen
    ("232371", "Regionalliga Nord"),
    ("231530", "Regionalliga Süd Stmk"),
    ("231655", "Regionalliga Süd Kärnten"),
    ("231974", "Regionalliga Ost"),
    ("232368", "Regionalliga West"),
    # Landesligen (Top-Liga je Bundesland)
    ("231506", "Landesliga Steiermark"),
    ("231940", "Wiener Stadtliga"),
    ("231756", "11teamsports 1. Landesliga (NÖ)"),
    ("231975", "Burgenland Energie Landesliga"),
    ("231619", "LT1 OÖ Liga"),
    ("231665", "Kärntner Liga"),
    ("231808", "Salzburger Liga"),
    ("231680", "1. HYPO TIROL Landesliga Ost"),
    ("232055", "VOL.AT-Eliteliga"),
    # Oberligen Steiermark
    ("231503", "Oberliga Nord"),
    ("231501", "Oberliga Mitte West"),
    ("231521", "Oberliga Süd Ost"),
    # Jugend
    ("232400", "ÖFB Jugendliga U18"),
    ("232399", "ÖFB Jugendliga U16"),
    ("232398", "ÖFB Jugendliga U15"),
    ("232407", "ÖFB Jugendregionalliga U18"),
    ("232406", "ÖFB Jugendregionalliga U16"),
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
