#!/usr/bin/env python3
"""
OEFB Spielbericht-Scraper
=========================

Scrapt Spielberichte von oefb.at aus der Druckansicht:

    https://www.oefb.at/Spiel/Druck/<SPIEL_ID>/

Extrahiert pro Spiel:
  * Grunddaten   – Datum, Uhrzeit, Bewerb/Runde, Spielort, Zuschauer, Schiedsrichter
  * Teams/Ergebnis – Heim/Gast, Endstand, Halbzeitstand
  * Aufstellungen – Startelf, Bank, Trainer je Team
  * Ereignisse    – Tore, Karten, Auswechslungen (mit Minute/Spieler)

WICHTIG ZU DEN SELEKTOREN
-------------------------
Die genauen CSS-Selektoren der OEFB-Seite sind hier *heuristisch* gesetzt
(label-basiert + Tabellen-Fallbacks), weil das HTML beim Bau dieses Scripts
nicht eingesehen werden konnte (Netzwerk-Sperre der Build-Umgebung).
Nach dem ersten echten Abruf bitte den Block `SELECTORS` und die Funktionen
unter "PARSER" anpassen. Mit `--save-html` kannst du das Roh-HTML speichern,
um die Struktur zu prüfen.

Beispiele
---------
    # Einzelnes Spiel, Ausgabe nach ./out
    python oefb_scraper.py --ids 3855332

    # ID-Bereich (inklusive), mit 1.5s Pause, Roh-HTML mitspeichern
    python oefb_scraper.py --id-range 3855330 3855340 --delay 1.5 --save-html

    # IDs aus Datei (eine pro Zeile)
    python oefb_scraper.py --ids-file ids.txt --format both --out-dir ergebnisse
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, Iterator

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("Fehlt: 'requests'. Installieren mit:  pip install -r requirements.txt")

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    sys.exit("Fehlt: 'beautifulsoup4'. Installieren mit:  pip install -r requirements.txt")


# --------------------------------------------------------------------------- #
# Konfiguration
# --------------------------------------------------------------------------- #

BASE_URL = "https://www.oefb.at/Spiel/Druck/{id}/"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-AT,de;q=0.9,en;q=0.5",
}

# Zentrale, leicht anzupassende Stellschrauben fuer das Parsing.
# Wenn das echte HTML bekannt ist, hier die CSS-Selektoren eintragen,
# dann greifen die spezifischen Pfade vor den Heuristiken.
SELECTORS: dict[str, str | None] = {
    # Container fuer die jeweilige Heimmannschaft / Gastmannschaft (optional)
    "home_team": None,
    "away_team": None,
    "scoreline": None,    # Element mit dem Endstand, z.B. "2:1"
    "lineup_home": None,  # Container Aufstellung Heim
    "lineup_away": None,  # Container Aufstellung Gast
}

log = logging.getLogger("oefb")


# --------------------------------------------------------------------------- #
# Datenmodell
# --------------------------------------------------------------------------- #

@dataclass
class Event:
    type: str               # "goal" | "yellow" | "yellow_red" | "red" | "substitution"
    minute: str | None = None
    team: str | None = None        # "home" | "away" wenn bestimmbar
    player: str | None = None
    player_out: str | None = None  # bei Auswechslung
    detail: str | None = None      # Freitext / Zusatz (z.B. "Elfmeter", Spielstand)


@dataclass
class Player:
    number: str | None = None
    name: str | None = None
    role: str = "starter"   # "starter" | "bench"


@dataclass
class TeamLineup:
    name: str | None = None
    coach: str | None = None
    starters: list[Player] = field(default_factory=list)
    bench: list[Player] = field(default_factory=list)


@dataclass
class Match:
    match_id: str
    url: str
    competition: str | None = None
    round: str | None = None
    date: str | None = None
    time: str | None = None
    venue: str | None = None
    spectators: str | None = None
    referee: str | None = None
    assistants: list[str] = field(default_factory=list)
    home_team: str | None = None
    away_team: str | None = None
    score: str | None = None
    score_home: int | None = None
    score_away: int | None = None
    halftime: str | None = None
    lineup_home: TeamLineup = field(default_factory=TeamLineup)
    lineup_away: TeamLineup = field(default_factory=TeamLineup)
    events: list[Event] = field(default_factory=list)
    # Diagnose
    ok: bool = True
    error: str | None = None


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

def fetch(session: requests.Session, match_id: str, timeout: float,
          retries: int, backoff: float) -> str:
    """Holt das HTML einer Druck-Seite, mit Retries + exponentiellem Backoff."""
    url = BASE_URL.format(id=match_id)
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code == 404:
                raise FileNotFoundError(f"404 fuer Spiel {match_id}")
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or resp.encoding
            return resp.text
        except FileNotFoundError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            wait = backoff * (2 ** (attempt - 1))
            log.warning("Versuch %d/%d fuer %s fehlgeschlagen: %s (warte %.1fs)",
                        attempt, retries, match_id, exc, wait)
            if attempt < retries:
                time.sleep(wait)
    raise RuntimeError(f"Konnte {url} nicht laden: {last_exc}")


# --------------------------------------------------------------------------- #
# Parser-Helfer
# --------------------------------------------------------------------------- #

def _text(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else ""


def _find_label_value(soup: BeautifulSoup, *labels: str) -> str | None:
    """Sucht einen Wert, der hinter einem Label-Text steht.

    Deckt mehrere gaengige Muster ab:
      <th>Schiedsrichter</th><td>Max Muster</td>
      <span class="label">Zuschauer:</span> 123
      "Schiedsrichter: Max Muster" als Fliesstext
    """
    label_pat = re.compile(r"^\s*(%s)\s*:?\s*$" % "|".join(re.escape(l) for l in labels), re.I)

    # 1) Tabellenzeilen: Label-Zelle -> naechste Zelle
    for cell in soup.find_all(["th", "td", "dt", "span", "strong", "b"]):
        if label_pat.match(_text(cell)):
            sib = cell.find_next_sibling(["td", "dd", "span", "div"])
            if sib and _text(sib):
                return _text(sib)
    # 2) "Label: Wert" als zusammenhaengender Text
    inline = re.compile(r"(?:%s)\s*:\s*([^\n|]+)" % "|".join(re.escape(l) for l in labels), re.I)
    m = inline.search(soup.get_text("\n"))
    if m:
        return m.group(1).strip(" .|")
    return None


def _parse_score(score: str | None) -> tuple[int | None, int | None]:
    if not score:
        return None, None
    m = re.search(r"(\d+)\s*[:\-]\s*(\d+)", score)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def _classify_event_type(text: str) -> str | None:
    t = text.lower()
    if "gelb-rot" in t or "gelb/rot" in t or "ampelkarte" in t:
        return "yellow_red"
    if "rote karte" in t or re.search(r"\brot\b", t):
        return "red"
    if "gelbe karte" in t or re.search(r"\bgelb\b", t):
        return "yellow"
    if "tor" in t or "treffer" in t or "elfmeter" in t:
        return "goal"
    if "wechsel" in t or "aus:" in t or "ein:" in t or "fuer" in t or "für" in t:
        return "substitution"
    return None


# --------------------------------------------------------------------------- #
# PARSER  (an echtes HTML anpassen!)
# --------------------------------------------------------------------------- #

def parse_match(html: str, match_id: str) -> Match:
    soup = BeautifulSoup(html, "html.parser")
    m = Match(match_id=str(match_id), url=BASE_URL.format(id=match_id))

    # --- Teams + Ergebnis ----------------------------------------------------
    # Heuristik: groesster "X : Y"-Treffer in der Naehe der Teamnamen.
    score_node = None
    if SELECTORS["scoreline"]:
        score_node = soup.select_one(SELECTORS["scoreline"])
    if score_node:
        m.score = _text(score_node)
    else:
        text = soup.get_text(" ")
        # 1) Bevorzugt Stand mit Leerzeichen um den Doppelpunkt ("2 : 1").
        sm = re.search(r"\b(\d{1,2})\s+:\s+(\d{1,2})\b", text)
        # 2) Sonst kompakter Stand, aber Uhrzeiten ausschliessen
        #    (Zweitwert mit genau 2 Stellen wie ":30" ist eher Uhrzeit).
        if not sm:
            for cand in re.finditer(r"\b(\d{1,2}):(\d{1,2})\b", text):
                after = text[cand.end():cand.end() + 5].lower()
                if len(cand.group(2)) == 2 and "uhr" in after:
                    continue
                if len(cand.group(2)) == 2 and int(cand.group(2)) >= 13:
                    continue  # plausibel Uhrzeit, kein Spielstand
                sm = cand
                break
        if sm:
            m.score = f"{sm.group(1)}:{sm.group(2)}"
    m.score_home, m.score_away = _parse_score(m.score)

    if SELECTORS["home_team"]:
        m.home_team = _text(soup.select_one(SELECTORS["home_team"]))
    if SELECTORS["away_team"]:
        m.away_team = _text(soup.select_one(SELECTORS["away_team"]))
    # Fallback Teamnamen: "Heim - Gast" / "Heim gegen Gast" im Titel/H1
    if not (m.home_team and m.away_team):
        title = _text(soup.find(["h1", "h2", "title"]))
        tm = re.search(r"(.+?)\s+(?:-|–|vs\.?|gegen)\s+(.+)", title)
        if tm:
            m.home_team = m.home_team or tm.group(1).strip()
            m.away_team = m.away_team or tm.group(2).strip()

    # --- Grunddaten ----------------------------------------------------------
    m.competition = _find_label_value(soup, "Bewerb", "Liga", "Wettbewerb")
    m.round = _find_label_value(soup, "Runde", "Spieltag")
    m.venue = _find_label_value(soup, "Spielort", "Stadion", "Sportplatz", "Austragungsort")
    m.spectators = _find_label_value(soup, "Zuschauer", "Zuseher")
    m.referee = _find_label_value(soup, "Schiedsrichter", "SR", "Referee")
    m.halftime = _find_label_value(soup, "Halbzeit", "Halbzeitstand", "HZ")

    # Datum / Uhrzeit
    full_text = soup.get_text(" ")
    dm = re.search(r"\b(\d{1,2}\.\d{1,2}\.\d{2,4})\b", full_text)
    if dm:
        m.date = dm.group(1)
    tmt = re.search(r"\b(\d{1,2}:\d{2})\s*(?:Uhr)?\b", full_text)
    if tmt:
        m.time = tmt.group(1)

    # Assistenten
    asst = _find_label_value(soup, "Assistenten", "Assistent", "SR-Assistent", "Linienrichter")
    if asst:
        m.assistants = [a.strip() for a in re.split(r"[;,/]| und ", asst) if a.strip()]

    # --- Aufstellungen -------------------------------------------------------
    m.lineup_home, m.lineup_away = _parse_lineups(soup)
    if m.lineup_home.name is None:
        m.lineup_home.name = m.home_team
    if m.lineup_away.name is None:
        m.lineup_away.name = m.away_team

    # --- Ereignisse ----------------------------------------------------------
    m.events = _parse_events(soup)

    return m


def _parse_players_from(container) -> list[Player]:
    """Extrahiert Spieler (Nr + Name) aus einem Container (ul/table/div)."""
    players: list[Player] = []
    if container is None:
        return players
    # Listenelemente oder Tabellenzeilen
    rows = container.find_all(["li", "tr"]) or [container]
    for row in rows:
        txt = _text(row)
        if not txt:
            continue
        nm = re.match(r"^(\d{1,2})[.\s)]+(.+)$", txt)
        if nm:
            players.append(Player(number=nm.group(1), name=nm.group(2).strip()))
        elif len(txt) > 1 and not re.match(r"(?i)(aufstellung|ersatz|bank|trainer)", txt):
            players.append(Player(name=txt))
    return players


def _parse_lineups(soup: BeautifulSoup) -> tuple[TeamLineup, TeamLineup]:
    home, away = TeamLineup(), TeamLineup()

    if SELECTORS["lineup_home"]:
        home.starters = _parse_players_from(soup.select_one(SELECTORS["lineup_home"]))
    if SELECTORS["lineup_away"]:
        away.starters = _parse_players_from(soup.select_one(SELECTORS["lineup_away"]))

    home.coach = _find_label_value(soup, "Trainer Heim") or None
    away.coach = _find_label_value(soup, "Trainer Gast") or None
    if not home.coach and not away.coach:
        # generisches Trainer-Label (kann beide treffen) – nur grob ablegen
        coach = _find_label_value(soup, "Trainer")
        if coach:
            home.coach = coach

    return home, away


def _parse_events(soup: BeautifulSoup) -> list[Event]:
    """Liest Tore/Karten/Wechsel.

    Heuristik: Zeilen mit einer Minute (z.B. "23.", "45+2", "67'") werden als
    Ereignis interpretiert; Typ wird aus dem Kontext/Text bestimmt.
    """
    events: list[Event] = []
    minute_pat = re.compile(r"^\s*(\d{1,3}(?:\+\d{1,2})?)[.'’]?\s*(.+)$")

    candidates = soup.find_all(["li", "tr", "p"])
    for node in candidates:
        txt = _text(node)
        if not txt:
            continue
        mm = minute_pat.match(txt)
        if not mm:
            continue
        minute, rest = mm.group(1), mm.group(2)
        etype = _classify_event_type(rest) or _classify_event_type(_text(node.parent))
        if not etype:
            continue
        ev = Event(type=etype, minute=minute)
        if etype == "substitution":
            # "aus: X ein: Y" – nicht-gierig bis zum naechsten Schluesselwort
            out_m = re.search(r"(?:aus|out)\s*:?\s*(.+?)\s*(?:ein|in)\s*:?\s*",
                              rest, re.I)
            in_m = re.search(r"(?:ein|in)\s*:?\s*([^,;|]+)\s*$", rest, re.I)
            ev.player = in_m.group(1).strip() if in_m else None
            ev.player_out = out_m.group(1).strip() if out_m else None
            if not (ev.player or ev.player_out):
                ev.detail = rest
        else:
            # Spielername = Text ohne Karten-/Tor-Schlagworte
            name = re.sub(r"(?i)(gelb-?rot|gelbe? karte|rote? karte|tor|treffer|elfmeter)", "", rest)
            ev.player = re.sub(r"[\s,;:|]+", " ", name).strip(" ,;:|-") or None
            ev.detail = rest
        events.append(ev)
    return events


# --------------------------------------------------------------------------- #
# Ausgabe
# --------------------------------------------------------------------------- #

def write_json(matches: list[Match], path: Path) -> None:
    data = [asdict(m) for m in matches]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("JSON geschrieben: %s (%d Spiele)", path, len(matches))


def write_csv(matches: list[Match], out_dir: Path) -> None:
    """Schreibt drei flache CSVs: matches, events, lineups."""
    # matches.csv – eine Zeile pro Spiel
    mfields = ["match_id", "url", "competition", "round", "date", "time", "venue",
               "spectators", "referee", "assistants", "home_team", "away_team",
               "score", "score_home", "score_away", "halftime",
               "coach_home", "coach_away", "ok", "error"]
    with (out_dir / "matches.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=mfields)
        w.writeheader()
        for m in matches:
            w.writerow({
                "match_id": m.match_id, "url": m.url, "competition": m.competition,
                "round": m.round, "date": m.date, "time": m.time, "venue": m.venue,
                "spectators": m.spectators, "referee": m.referee,
                "assistants": "; ".join(m.assistants),
                "home_team": m.home_team, "away_team": m.away_team,
                "score": m.score, "score_home": m.score_home, "score_away": m.score_away,
                "halftime": m.halftime,
                "coach_home": m.lineup_home.coach, "coach_away": m.lineup_away.coach,
                "ok": m.ok, "error": m.error,
            })

    # events.csv – eine Zeile pro Ereignis
    with (out_dir / "events.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["match_id", "type", "minute", "team", "player", "player_out", "detail"])
        for m in matches:
            for e in m.events:
                w.writerow([m.match_id, e.type, e.minute, e.team, e.player, e.player_out, e.detail])

    # lineups.csv – eine Zeile pro Spieler
    with (out_dir / "lineups.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["match_id", "side", "team", "role", "number", "player", "coach"])
        for m in matches:
            for side, lu in (("home", m.lineup_home), ("away", m.lineup_away)):
                for p in lu.starters + lu.bench:
                    w.writerow([m.match_id, side, lu.name, p.role, p.number, p.name, lu.coach])

    log.info("CSV geschrieben: matches.csv, events.csv, lineups.csv in %s", out_dir)


# --------------------------------------------------------------------------- #
# ID-Quellen
# --------------------------------------------------------------------------- #

def resolve_ids(args: argparse.Namespace) -> list[str]:
    ids: list[str] = []
    if args.ids:
        ids.extend(str(i) for i in args.ids)
    if args.id_range:
        start, end = args.id_range
        step = 1 if end >= start else -1
        ids.extend(str(i) for i in range(start, end + step, step))
    if args.ids_file:
        for line in Path(args.ids_file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                ids.append(line)
    # Duplikate entfernen, Reihenfolge wahren
    seen: set[str] = set()
    return [i for i in ids if not (i in seen or seen.add(i))]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Scrapt OEFB-Spielberichte aus der Druckansicht (/Spiel/Druck/<id>/).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    src = p.add_argument_group("Spiel-IDs (mindestens eine Quelle noetig)")
    src.add_argument("--ids", nargs="+", type=int, metavar="ID", help="Einzelne Spiel-IDs")
    src.add_argument("--id-range", nargs=2, type=int, metavar=("START", "END"),
                     help="ID-Bereich inklusive, z.B. --id-range 3855330 3855340")
    src.add_argument("--ids-file", metavar="DATEI", help="Datei mit einer ID pro Zeile")

    out = p.add_argument_group("Ausgabe")
    out.add_argument("--out-dir", default="out", help="Zielverzeichnis (Default: out)")
    out.add_argument("--format", choices=["json", "csv", "both"], default="both",
                     help="Ausgabeformat (Default: both)")
    out.add_argument("--save-html", action="store_true",
                     help="Roh-HTML je Spiel unter <out>/html/ speichern (Debug)")

    net = p.add_argument_group("Netzwerk / Verhalten")
    net.add_argument("--delay", type=float, default=1.0,
                     help="Pause zwischen Anfragen in Sekunden (Default: 1.0)")
    net.add_argument("--timeout", type=float, default=30.0, help="HTTP-Timeout (Default: 30)")
    net.add_argument("--retries", type=int, default=4, help="Anzahl Versuche (Default: 4)")
    net.add_argument("--backoff", type=float, default=2.0,
                     help="Backoff-Basis in Sekunden (Default: 2.0)")
    net.add_argument("-v", "--verbose", action="store_true", help="Mehr Log-Ausgaben")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    ids = resolve_ids(args)
    if not ids:
        log.error("Keine IDs angegeben. Nutze --ids / --id-range / --ids-file.")
        return 2
    log.info("%d Spiel(e) zu scrapen.", len(ids))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    html_dir = out_dir / "html"
    if args.save_html:
        html_dir.mkdir(exist_ok=True)

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    matches: list[Match] = []
    for idx, mid in enumerate(ids, 1):
        log.info("[%d/%d] Spiel %s", idx, len(ids), mid)
        try:
            html = fetch(session, mid, args.timeout, args.retries, args.backoff)
            if args.save_html:
                (html_dir / f"{mid}.html").write_text(html, encoding="utf-8")
            match = parse_match(html, mid)
            log.debug("  -> %s %s %s | %d Ereignisse",
                      match.home_team, match.score, match.away_team, len(match.events))
            matches.append(match)
        except FileNotFoundError as exc:
            log.warning("  uebersprungen: %s", exc)
            matches.append(Match(match_id=str(mid), url=BASE_URL.format(id=mid),
                                 ok=False, error="404 not found"))
        except Exception as exc:  # noqa: BLE001
            log.error("  Fehler bei %s: %s", mid, exc)
            matches.append(Match(match_id=str(mid), url=BASE_URL.format(id=mid),
                                 ok=False, error=str(exc)))
        if idx < len(ids) and args.delay > 0:
            time.sleep(args.delay)

    if args.format in ("json", "both"):
        write_json(matches, out_dir / "matches.json")
    if args.format in ("csv", "both"):
        write_csv(matches, out_dir)

    ok = sum(1 for m in matches if m.ok)
    log.info("Fertig. %d/%d erfolgreich.", ok, len(matches))
    return 0


if __name__ == "__main__":
    sys.exit(main())
