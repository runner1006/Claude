#!/usr/bin/env python3
"""Erzeugt data/player_extras.json fuer die Profilseite des Dashboards.

Kompakte Teilmenge von players_profiles.json (103 MB -> ~18 MB), je Spieler:
    v: Vereins-Historie  [[verein, ab_ms, landCode], ...]
    e: Saison-Erfolge    [[saison, verein, kategorie, ziel], ...]

Aufruf: python build_extras.py  (nach player_ages.py laufen lassen)
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profiles", default="data/players_profiles.json")
    p.add_argument("-o", "--out", default="data/player_extras.json")
    args = p.parse_args(argv)

    prof = json.load(open(args.profiles, encoding="utf-8"))
    extras = {}
    for pid, pl in prof.items():
        v = [[c.get("verein"), c.get("ab"), c.get("landCode")]
             for c in (pl.get("vereine") or [])]
        e = [[x.get("saison"), x.get("verein"), x.get("kategorie"), x.get("ziel")]
             for x in (pl.get("erfolge") or [])]
        if v or e:
            extras[pid] = {"v": v, "e": e}

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(extras, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(extras)} Spieler -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
