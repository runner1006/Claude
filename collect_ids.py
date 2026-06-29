#!/usr/bin/env python3
"""
OEFB Spiel-ID-Sammler
=====================

Findet die Spiel-IDs einer Liga/eines Bewerbs ueber die JSON-Datenservice-API
von oefb.at und schreibt sie in eine Datei (eine ID pro Zeile), die direkt mit

    python oefb_scraper.py --ids-file ids.txt

weiterverarbeitet werden kann.

Hintergrund
-----------
Die Spielplan-/Ergebnis-Widgets auf oefb.at laden ihre Daten von einer REST-API:

    /datenservice/rest/oefb/spielbetrieb/spielplanBewerbByPublicUid/<BEWERB>;runde=<N>

Die Antwort ist sauberes JSON mit `spiele` (Termine) und `ergebnisse` (gespielt);
jeder Eintrag enthaelt einen Spielbericht-Link `.../Spielbericht/<SPIEL_ID>/`.
Das Feld `runden` listet alle verfuegbaren Runden.

Die Anubis-Bot-Schutz-Challenge wird automatisch geloest (via oefb_scraper).

Beispiele
---------
    # Alle Bewerbe (ID + Titel) auflisten, um die richtige Bewerb-ID zu finden:
    python collect_ids.py --list

    # Alle Runden der Salzburger Liga sammeln -> ids.txt
    python collect_ids.py --bewerb 226782 -o ids.txt

    # Nur Runden 1-5, danach direkt scrapen:
    python collect_ids.py --bewerb 226782 --rounds 1-5 -o ids.txt
    python oefb_scraper.py --ids-file ids.txt --delay 2
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time

import requests

import oefb_scraper as oefb

OVERVIEW_URL = "https://www.oefb.at/bewerbe/"
API_URL = ("https://www.oefb.at/datenservice/rest/oefb/spielbetrieb/"
           "spielplanBewerbByPublicUid/{bewerb};runde={runde}")
_SPIELBERICHT_RE = re.compile(r"/Spielbericht/(\d+)")


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


def list_bewerbe(session: requests.Session) -> list[tuple[str, str]]:
    """Liest Bewerb-IDs + Titel aus der Bewerbe-Uebersicht."""
    html = get(session, OVERVIEW_URL)
    ids = list(dict.fromkeys(re.findall(r"/bewerbe/Bewerb/(\d+)", html)))
    result: list[tuple[str, str]] = []
    for bid in ids:
        title = bid
        try:  # Titel kommt am guenstigsten aus der API selbst
            data = fetch_round(session, bid, 1)
            title = data.get("title") or bid
        except Exception:  # noqa: BLE001
            pass
        result.append((bid, title))
    return result


def fetch_round(session: requests.Session, bewerb: str, runde: int) -> dict:
    return json.loads(get(session, API_URL.format(bewerb=bewerb, runde=runde)))


def _round_num(r) -> int | None:
    """Rundennummer aus dem `runden`-Eintrag (int oder Dict)."""
    if isinstance(r, int):
        return r
    if isinstance(r, dict):
        for k in ("runde", "nummer", "number", "value", "id"):
            if isinstance(r.get(k), int):
                return r[k]
    return None


def ids_from_round(data: dict) -> list[str]:
    """Zieht alle Spiel-IDs (Ergebnisse + Termine) aus einer Runde."""
    found: list[str] = []
    for entry in (data.get("ergebnisse") or []) + (data.get("spiele") or []):
        # bevorzugt strukturierte Links, sonst das gesamte Entry-JSON absuchen
        blob = json.dumps(entry, ensure_ascii=False)
        found.extend(_SPIELBERICHT_RE.findall(blob))
    return found


def collect(session: requests.Session, bewerb: str, rounds: list[int] | None,
            delay: float) -> list[str]:
    # Erste Runde holen, um Titel + verfuegbare Runden zu kennen.
    first = fetch_round(session, bewerb, rounds[0] if rounds else 1)
    title = first.get("title", bewerb)
    available = [n for n in (_round_num(r) for r in first.get("runden") or []) if n]
    if rounds is None:
        rounds = available or [1]
    print(f"Bewerb {bewerb}: {title} — sammle Runden {rounds[0]}..{rounds[-1]} "
          f"({len(available)} verfuegbar)", file=sys.stderr)

    seen: set[str] = set()
    ordered: list[str] = []
    for i, runde in enumerate(rounds):
        # erste Runde wurde oben schon geholt -> wiederverwenden
        data = first if i == 0 else fetch_round(session, bewerb, runde)
        ids = ids_from_round(data)
        new = [i for i in ids if not (i in seen or seen.add(i))]
        ordered.extend(new)
        print(f"  Runde {runde:>2}: {len(ids):>3} Spiele, {len(new):>3} neu "
              f"(gesamt {len(ordered)})", file=sys.stderr)
        if i < len(rounds) - 1 and delay > 0:
            time.sleep(delay)
    return ordered


def parse_rounds(spec: str | None) -> list[int] | None:
    if not spec:
        return None
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out or None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Sammelt OEFB-Spiel-IDs eines Bewerbs ueber die Datenservice-API.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--list", action="store_true",
                   help="Alle Bewerbe (ID + Titel) auflisten und beenden")
    p.add_argument("--bewerb", metavar="ID", help="Bewerb-ID (siehe --list)")
    p.add_argument("--rounds", metavar="SPEC",
                   help="Runden, z.B. '1-5' oder '1,3,7' (Default: alle)")
    p.add_argument("-o", "--out", metavar="DATEI", default="ids.txt",
                   help="Zieldatei fuer die IDs (Default: ids.txt)")
    p.add_argument("--delay", type=float, default=1.0,
                   help="Pause zwischen Runden-Abfragen in Sek. (Default: 1.0)")
    args = p.parse_args(argv)

    session = make_session()

    if args.list:
        for bid, title in list_bewerbe(session):
            print(f"{bid}\t{title}")
        return 0

    if not args.bewerb:
        p.error("--bewerb erforderlich (oder --list zum Auffinden der ID).")

    ids = collect(session, args.bewerb, parse_rounds(args.rounds), args.delay)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(ids) + ("\n" if ids else ""))
    print(f"{len(ids)} Spiel-IDs geschrieben -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
