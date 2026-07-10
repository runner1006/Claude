#!/usr/bin/env python3
"""Repariert unvollstaendige Tor-/Event-Timelines.

Hintergrund: Die Druckansicht (Quelle von oefb_scraper) liefert fuer viele
Landesverbaende keine Tor-Minuten – ~35 % der Matches haben Tore laut Score,
aber keine (numerischen) Tor-Events. Das Spielbericht-JSON (appPreloads
`gameData`, dieselbe Quelle wie player_ages) enthaelt die Events MIT Minuten.

Dieses Skript laedt fuer alle betroffenen Matches den Spielbericht, extrahiert
die Events neu und ersetzt sie in data/events.csv und data/matches.json.

Robust gegen Abbruch: je Match wird das Ergebnis sofort als JSONL-Zeile in
--work geschrieben; ein Neustart ueberspringt bereits geladene Matches.
`--finalize` wendet nur die vorhandene Work-Datei an (ohne neue Downloads).

Aufruf:
    python fix_events.py            # ermitteln + laden + anwenden
    python fix_events.py --finalize # nur Work-Datei anwenden
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time

import player_ages as pa

csv.field_size_limit(10_000_000)

log = pa.log

# gameData-Typ -> events.csv-Typ
_TYPE_MAP = {
    "goal": "goal",
    "goal-own": "goal",
    "goal-penalty": "goal",
    "card-yellow": "yellow",
    "card-yellowred": "yellow_red",
    "card-yellow-red": "yellow_red",
    "card-red": "red",
    "playerchange": "substitution",
}
_SIDE = {"a": "home", "b": "away"}


def find_incomplete(events_p: str, matches_p: str) -> list[str]:
    """Match-IDs, bei denen numerische Tor-Events < Score-Summe."""
    numeric = {}
    for e in csv.DictReader(open(events_p, encoding="utf-8")):
        if e["type"] == "goal" and e["minute"].isdigit():
            numeric[e["match_id"]] = numeric.get(e["match_id"], 0) + 1
    bad = []
    for r in csv.DictReader(open(matches_p, encoding="utf-8")):
        sc = int(r.get("score_home") or 0) + int(r.get("score_away") or 0)
        if sc > 0 and numeric.get(r["match_id"], 0) < sc:
            bad.append(r["match_id"])
    return bad


def events_from_gamedata(gd: list[dict]) -> list[dict]:
    """gameData -> Zeilen im events.csv-Schema.

    WICHTIG: Bei Toren nennt `team` das Team des SCHUETZEN. Bei Eigentoren
    (`eigentor: true`) zaehlt das Tor fuer die Gegenseite -> Seite flippen
    (validiert an Match 3864725: 78' Eigentor Koch, spielstand 2:2).
    """
    out = []
    for e in gd or []:
        t = _TYPE_MAP.get(e.get("type") or "")
        if not t:
            continue
        mn = pa._real_minute(e)
        side = _SIDE.get(e.get("team") or "", "")
        detail = e.get("hinweis") or ""
        if t == "goal" and e.get("eigentor") and side:
            side = "away" if side == "home" else "home"   # Eigentor -> Gegenseite
            detail = detail or "Eigentor"
        out.append({
            "type": t,
            "minute": "" if mn is None else str(mn),
            "team": side,
            "player": e.get("playerPrimary") or "",
            "player_out": (e.get("playerSecondary") or "") if t == "substitution" else "",
            "detail": detail,
        })
    return out


def load_work(path: str) -> dict[str, list[dict]]:
    done = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                done[obj["match_id"]] = obj["events"]
            except (ValueError, KeyError):
                continue
    return done


def apply_work(work: dict[str, list[dict]], events_p: str, matches_p: str) -> None:
    """Ersetzt Events der reparierten Matches in events.csv und matches.json.

    Sicherheit: nur Match-IDs anwenden, die im Datensatz (matches.json)
    existieren – verhindert Waisen-Zeilen durch versehentlich geladene IDs.
    """
    known = {str(m.get("match_id"))
             for m in json.load(open(matches_p, encoding="utf-8"))}
    work = {mid: evs for mid, evs in work.items() if mid in known}
    repaired = set(work)
    # events.csv: alte Zeilen der reparierten Matches raus, neue rein
    with open(events_p, encoding="utf-8") as f:
        rd = csv.DictReader(f)
        fields = rd.fieldnames
        keep = [r for r in rd if r["match_id"] not in repaired]
    with open(events_p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(keep)
        for mid, evs in work.items():
            for e in evs:
                w.writerow({"match_id": mid, **e})
    log.info("events.csv: %d Matches ersetzt (%d Zeilen unangetastet).",
             len(repaired), len(keep))
    # matches.json: events-Arrays ersetzen
    matches = json.load(open(matches_p, encoding="utf-8"))
    n = 0
    for m in matches:
        mid = str(m.get("match_id"))
        if mid in work:
            m["events"] = work[mid]
            n += 1
    json.dump(matches, open(matches_p, "w", encoding="utf-8"), ensure_ascii=False)
    log.info("matches.json: %d events-Arrays ersetzt.", n)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--events", default="data/events.csv")
    p.add_argument("--matches", default="data/matches.csv")
    p.add_argument("--matches-json", default="data/matches.json")
    p.add_argument("--work", default="data/fix_events_work.jsonl")
    p.add_argument("--ids", nargs="*", help="nur diese Match-IDs reparieren")
    p.add_argument("--delay", type=float, default=0.6)
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--finalize", action="store_true",
                   help="nur vorhandene Work-Datei anwenden, nichts laden")
    p.add_argument("--no-apply", action="store_true",
                   help="nur laden, events.csv/matches.json nicht anfassen")
    args = p.parse_args(argv)

    pa.oefb.logging.basicConfig(level=pa.oefb.logging.INFO,
                                format="%(asctime)s %(levelname)s %(message)s",
                                datefmt="%H:%M:%S")

    work = load_work(args.work)
    if not args.finalize:
        bad = args.ids if args.ids else find_incomplete(args.events, args.matches)
        todo = [m for m in bad if m not in work]
        log.info("Unvollstaendig: %d Matches, davon neu zu laden: %d "
                 "(bereits in Work-Datei: %d)", len(bad), len(todo), len(work))
        scores = {r["match_id"]: (int(r.get("score_home") or 0),
                                  int(r.get("score_away") or 0))
                  for r in csv.DictReader(open(args.matches, encoding="utf-8"))}
        session = pa.make_session()
        wf = open(args.work, "a", encoding="utf-8")
        ok = fail = mismatch = 0
        for i, mid in enumerate(todo, 1):
            try:
                html = pa.get(session, pa.REPORT_URL.format(id=mid), args.timeout)
                data = pa._find_match_data(html)
                evs = events_from_gamedata((data or {}).get("gameData"))
                # nur uebernehmen, wenn wir mind. 1 Tor-Event mit Minute gewonnen haben
                if any(e["type"] == "goal" and e["minute"].isdigit() for e in evs):
                    gh = sum(1 for e in evs if e["type"] == "goal" and e["team"] == "home")
                    ga = sum(1 for e in evs if e["type"] == "goal" and e["team"] == "away")
                    if scores.get(mid) and (gh, ga) != scores[mid]:
                        mismatch += 1  # Diagnose; Dashboard behandelt Restluecken selbst
                    work[mid] = evs
                    wf.write(json.dumps({"match_id": mid, "events": evs},
                                        ensure_ascii=False) + "\n")
                    wf.flush()
                    ok += 1
                else:
                    fail += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("[%d/%d] %s: %s", i, len(todo), mid, exc)
                fail += 1
            if i % 100 == 0:
                log.info("[%d/%d] repariert=%d ohne-Gewinn=%d score-mismatch=%d",
                         i, len(todo), ok, fail, mismatch)
            if args.delay > 0:
                time.sleep(args.delay)
        wf.close()
        log.info("Laden fertig: %d repariert, %d ohne Gewinn/Fehler, %d Score-Abweichungen.",
                 ok, fail, mismatch)

    if not args.no_apply and work:
        apply_work(work, args.events, args.matches_json)
    log.info("FERTIG. Work-Datei: %s (%d Matches).", args.work, len(work))
    return 0


if __name__ == "__main__":
    sys.exit(main())
