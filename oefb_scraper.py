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
import hashlib
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, Iterator
from urllib.parse import urljoin

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
    captain: bool = False


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

class ChallengeError(RuntimeError):
    """Die Antwort war eine Bot-Schutz-Challenge (z.B. Anubis), keine Spielseite."""


# Marker, an denen eine Anubis-/Bot-Schutz-Challenge-Seite erkennbar ist.
# Die echte Druckseite enthaelt keinen dieser Strings.
_CHALLENGE_MARKERS = (
    "anubis_challenge",
    "anubis_version",
    "/.within.website/",
    "Dein Browser wird geprüft",
    "Making sure you're not a bot",
)


def _detect_challenge(html: str) -> str | None:
    """Gibt den gefundenen Challenge-Marker zurueck, sonst None.

    Eine echte Spielseite liefert keinen dieser Marker; taucht einer auf,
    haben wir statt der Daten die Proof-of-Work-Challenge erhalten.
    """
    head = html[:8192]  # Challenge-Seiten sind klein; Marker stehen ganz oben.
    for marker in _CHALLENGE_MARKERS:
        if marker in head:
            return marker
    return None


# --------------------------------------------------------------------------- #
# Anubis Proof-of-Work-Loeser
# --------------------------------------------------------------------------- #
#
# Anubis (v1.x, Algorithmus "fast"/"slow") stellt eine Hashcash-artige PoW:
# Gesucht ist eine nonce, sodass SHA-256(randomData + str(nonce)) mit
# `difficulty` fuehrenden Null-*Nibbles* (Hex-Nullen) beginnt. Die Logik ist
# 1:1 aus dem Client-Worker (sha256-webcrypto.mjs) nachgebaut:
#   - die ersten floor(difficulty/2) Bytes muessen 0x00 sein
#   - bei ungerader difficulty zusaetzlich das High-Nibble des naechsten Bytes
# Der gefundene Hash (Hex) + nonce werden an /api/pass-challenge geschickt;
# der Server setzt daraufhin das Auth-Cookie und leitet zur Spielseite zurueck.

_ANUBIS_CHALLENGE_RE = re.compile(
    r'<script id="anubis_challenge"[^>]*>(.*?)</script>', re.S
)
_ANUBIS_API = "/.within.website/x/cmd/anubis/api/pass-challenge"


def _apply_encoding(resp: requests.Response) -> None:
    """Setzt resp.encoding robust.

    Deklariert der Server eine Charset im Content-Type-Header, wird diese
    bevorzugt (requests hat sie bereits gesetzt). Nur ohne Deklaration wird
    auf die Heuristik (apparent_encoding) zurueckgegriffen – sonst raet
    chardet bei UTF-8-Seiten gern CP949 o.ae. und erzeugt Mojibake.
    """
    content_type = resp.headers.get("Content-Type", "").lower()
    if "charset=" not in content_type:
        resp.encoding = resp.apparent_encoding or resp.encoding


def _parse_anubis_challenge(html: str) -> dict | None:
    """Extrahiert das anubis_challenge-JSON aus der Challenge-Seite."""
    m = _ANUBIS_CHALLENGE_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1).strip())
    except (ValueError, TypeError):
        return None


def _solve_anubis_pow(random_data: str, difficulty: int,
                      max_iter: int = 50_000_000) -> tuple[int, str]:
    """Brute-forced die nonce; gibt (nonce, hash_hex) zurueck.

    Spiegelt die Pruefung des Clients: floor(difficulty/2) Null-Bytes,
    bei ungerader difficulty zusaetzlich das obere Nibble des Folgebytes.
    """
    full_bytes = difficulty // 2
    odd = difficulty % 2 == 1
    prefix = random_data.encode("utf-8")
    for nonce in range(max_iter):
        digest = hashlib.sha256(prefix + str(nonce).encode("ascii")).digest()
        if any(digest[i] != 0 for i in range(full_bytes)):
            continue
        if odd and (digest[full_bytes] >> 4) != 0:
            continue
        return nonce, digest.hex()
    raise ChallengeError(
        f"PoW nicht geloest nach {max_iter} Versuchen (difficulty={difficulty})."
    )


def solve_challenge(session: requests.Session, page_url: str, html: str,
                    timeout: float) -> str:
    """Loest die Anubis-Challenge und liefert das HTML der echten Spielseite.

    Holt das Auth-Cookie via /api/pass-challenge (im selben Session-Jar) und
    folgt der Weiterleitung zurueck zur Druckseite.
    """
    obj = _parse_anubis_challenge(html)
    if not obj:
        raise ChallengeError("anubis_challenge-Block nicht gefunden/parsebar.")
    chal = obj.get("challenge") or {}
    rules = obj.get("rules") or {}
    random_data = chal.get("randomData")
    difficulty = int(rules.get("difficulty") or chal.get("difficulty") or 0)
    cid = chal.get("id")
    if not (random_data and difficulty and cid):
        raise ChallengeError("Challenge unvollstaendig (randomData/difficulty/id).")

    t0 = time.monotonic()
    nonce, response = _solve_anubis_pow(random_data, difficulty)
    elapsed_ms = max(int((time.monotonic() - t0) * 1000), 1)
    log.info("  PoW geloest: difficulty=%d nonce=%d in %dms", difficulty, nonce, elapsed_ms)

    api_url = urljoin(page_url, _ANUBIS_API)
    params = {
        "id": cid,
        "response": response,
        "nonce": nonce,
        "redir": page_url,
        "elapsedTime": elapsed_ms,
    }
    # Folgt der 302-Weiterleitung auf die Spielseite; Cookie landet im Jar.
    resp = session.get(api_url, params=params, timeout=timeout)
    resp.raise_for_status()
    _apply_encoding(resp)
    if _detect_challenge(resp.text):
        raise ChallengeError("Nach PoW-Einreichung weiterhin Challenge-Seite "
                             "(Cookie/Bindung abgelehnt).")
    return resp.text


def fetch(session: requests.Session, match_id: str, timeout: float,
          retries: int, backoff: float, solve: bool = True) -> str:
    """Holt das HTML einer Druck-Seite, mit Retries + exponentiellem Backoff.

    Bei einer Anubis-Challenge wird – sofern `solve` aktiv ist – die
    Proof-of-Work geloest und die Seite danach erneut geladen.
    """
    url = BASE_URL.format(id=match_id)
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code == 404:
                raise FileNotFoundError(f"404 fuer Spiel {match_id}")
            resp.raise_for_status()
            _apply_encoding(resp)
            marker = _detect_challenge(resp.text)
            if marker:
                if solve:
                    log.info("  Anubis-Challenge erkannt (Marker '%s') – loese PoW...", marker)
                    return solve_challenge(session, url, resp.text, timeout)
                # Erneutes Laden loest dasselbe Problem nicht – nicht retrien.
                raise ChallengeError(
                    f"Bot-Schutz-Challenge erhalten (Marker '{marker}'); "
                    f"keine Spieldaten abrufbar ohne Loesen der Proof-of-Work."
                )
            return resp.text
        except (FileNotFoundError, ChallengeError):
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
# PARSER – OEFB Druckansicht (echte Struktur)
# --------------------------------------------------------------------------- #
#
# Die Druckseite liefert ein App-Geruest; der eigentliche Spielbericht steckt
# als escapetes HTML in   SG.container.appPreloads['<id>'] = [{"html": "..."}].
# Darin sind echte Texte zusaetzlich mit <span style="display:none">muell</span>
# durchsetzt (Anti-Scraping). Nach dem Entfernen dieser Decoys liefern die
# Tabellen saubere Daten:
#   * table.headlinecontent : "Heim : Gast - Endstand (Halbzeit)" + Meta-Zeile
#   * Spieler-Tabellen (Blatt-Tabellen, 9 Spalten):
#       RNr | Spieler | K | Aus | Ein | Gelb | GelbRot | Rot | Tore
#     Reihenfolge: Heim-Start, Gast-Start, Heim-Ersatz, Gast-Ersatz
#   * "TR <Name>"-Zeilen = Trainer; "Schiedsrichter"/"Assistent 1|2" = Offizielle

_DISPLAY_NONE_RE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0", re.I
)
_PRELOAD_RE = re.compile(r"appPreloads\['?-?\d+'?\]\s*=\s*")


def _cell(node) -> str:
    """Zellen-Text rekonstruieren.

    Wichtig: KEIN strip pro Textknoten (sonst gehen echte Trennleerzeichen
    verloren, die zwischen Decoy-Spans liegen). Stattdessen leer joinen und
    erst am Ende Whitespace zusammenfassen.
    """
    return re.sub(r"\s+", " ", node.get_text("")).strip() if node else ""


def _extract_report_soup(html: str) -> BeautifulSoup | None:
    """Holt das eingebettete Spielbericht-HTML und entfernt die Decoy-Spans."""
    m = _PRELOAD_RE.search(html)
    if not m:
        return None
    start = html.find("[", m.end())
    if start == -1:
        return None
    try:
        arr, _ = json.JSONDecoder().raw_decode(html, start)
    except ValueError:
        return None
    inner = next((it["html"] for it in arr
                  if isinstance(it, dict) and it.get("html")), None)
    if not inner:
        return None
    soup = BeautifulSoup(inner, "html.parser")
    for el in soup.find_all(style=_DISPLAY_NONE_RE):
        el.decompose()
    return soup


def _strip_contact(value: str) -> str:
    """Entfernt angehaengte Telefonnummern in Klammern: 'Name (06...)' -> 'Name'."""
    return re.sub(r"\s*\(.*?\)\s*$", "", value).strip()


def _split_minutes(value: str) -> list[str]:
    """'72, 77' -> ['72','77']; 'HZ' -> ['HZ']; '' -> []."""
    return [p for p in re.split(r"[,\s]+", value.strip()) if p] if value else []


def _minute_key(minute: str | None) -> float:
    """Sortierschluessel; 'HZ' (Halbzeit) ~ 45, '45+2' -> 45.x."""
    if not minute:
        return 999.0
    if minute.upper() == "HZ":
        return 45.5
    mm = re.match(r"(\d+)(?:\+(\d+))?", minute)
    if mm:
        return int(mm.group(1)) + (int(mm.group(2)) / 100 if mm.group(2) else 0)
    return 999.0


def _leaf_player_tables(soup: BeautifulSoup) -> list:
    """Blatt-Tabellen (ohne verschachtelte Tabelle) mit Spieler-Zeilen."""
    tables = []
    for tb in soup.find_all("table"):
        if tb.find("table") is not None:
            continue  # nur Blatt-Tabellen, sonst doppeln sich die Spieler
        has_player = any(
            tr.find_all("td") and re.fullmatch(r"\d{1,2}", _cell(tr.find("td") or tb))
            for tr in tb.find_all("tr")
        )
        if has_player:
            tables.append(tb)
    return tables


def _collect_players(tb, role: str) -> list[dict]:
    """Liest die 9-Spalten-Zeilen einer Spieler-Tabelle in Rohdicts."""
    recs: list[dict] = []
    for tr in tb.find_all("tr"):
        cells = [_cell(td) for td in tr.find_all("td")]
        if len(cells) < 2 or not re.fullmatch(r"\d{1,2}", cells[0]) or not cells[1]:
            continue  # Kopf-/Leerzeile
        g = lambda i: cells[i] if i < len(cells) else ""
        recs.append({
            "number": cells[0], "name": cells[1], "captain": g(2).upper() == "X",
            "out": g(3), "in": g(4),
            "yellow": g(5), "yellow_red": g(6), "red": g(7), "goals": g(8),
            "role": role,
        })
    return recs


def _team_events(recs: list[dict], team: str) -> list[Event]:
    """Erzeugt Tore-, Karten- und Wechsel-Ereignisse aus den Spieler-Rohdaten."""
    events: list[Event] = []
    outs: list[tuple[str, str]] = []
    ins_by_minute: dict[str, list[str]] = {}
    for r in recs:
        for minute in _split_minutes(r["goals"]):
            events.append(Event("goal", minute=minute, team=team, player=r["name"]))
        for col, etype in (("yellow", "yellow"), ("yellow_red", "yellow_red"),
                           ("red", "red")):
            for minute in _split_minutes(r[col]):
                events.append(Event(etype, minute=minute, team=team, player=r["name"]))
        if r["out"]:
            outs.append((r["out"], r["name"]))
        if r["in"]:
            ins_by_minute.setdefault(r["in"], []).append(r["name"])
    # Ein-/Auswechslung paaren (gleiche Minute, gleiches Team)
    for minute, name_out in outs:
        partners = ins_by_minute.get(minute)
        name_in = partners.pop(0) if partners else None
        events.append(Event("substitution", minute=minute, team=team,
                            player=name_in, player_out=name_out))
    for minute, names in ins_by_minute.items():
        for name_in in names:  # Einwechslungen ohne zugeordnete Auswechslung
            events.append(Event("substitution", minute=minute, team=team, player=name_in))
    return events


def _parse_report(soup: BeautifulSoup, m: Match) -> None:
    """Befuellt `m` aus dem entschluesselten Spielbericht-HTML."""
    # --- Kopf: Teams, Ergebnis, Meta ----------------------------------------
    head = soup.find(class_="headlinecontent")
    if head:
        rows = head.find_all("tr")
        line = _cell(rows[0]) if rows else ""
        hm = re.match(r"^(.*?)\s*:\s*(.*?)\s*-\s*(\d+:\d+)(?:\s*\((\d+:\d+)\))?", line)
        if hm:
            m.home_team, m.away_team = hm.group(1).strip(), hm.group(2).strip()
            m.score, m.halftime = hm.group(3), hm.group(4)
        meta = [c for r in rows[1:] for c in (_cell(td) for td in r.find_all(["td", "th"])) if c]
        blob = " ".join(meta)
        dm = re.search(r"\b(\d{1,2}\.\d{1,2}\.\d{2,4})\b", blob)
        if dm:
            m.date = dm.group(1)
        tm = re.search(r"\b(\d{1,2}:\d{2})\b", blob)
        if tm:
            m.time = tm.group(1)
        sm = re.search(r"(\d+)\s*Zuschauer", blob)
        if sm:
            m.spectators = sm.group(1)
        for c in meta:  # Bewerb: erste Zelle ohne Datum/Zeit/Zuschauer
            if c not in (m.date, m.time) and not re.search(r"\d{1,2}\.\d{1,2}\.|Zuschauer|^\d+:\d{2}$", c):
                m.competition = c
                break
        for c in meta:  # Spielort: Zelle mit Klammer (Ort (Sportplatz))
            if "(" in c and "Zuschauer" not in c and c != m.competition:
                m.venue = c
                break
        rm = re.search(r"(\d+)\.\s*Runde", blob)
        if rm:
            m.round = rm.group(0)
    m.score_home, m.score_away = _parse_score(m.score)

    # --- Aufstellungen + Ereignisse -----------------------------------------
    tables = _leaf_player_tables(soup)
    # Reihenfolge laut Template: Heim-Start, Gast-Start, Heim-Ersatz, Gast-Ersatz
    home_start = _collect_players(tables[0], "starter") if len(tables) > 0 else []
    away_start = _collect_players(tables[1], "starter") if len(tables) > 1 else []
    home_bench = _collect_players(tables[2], "bench") if len(tables) > 2 else []
    away_bench = _collect_players(tables[3], "bench") if len(tables) > 3 else []

    def _lineup(name, starters, bench):
        lu = TeamLineup(name=name)
        lu.starters = [Player(r["number"], r["name"], "starter", r["captain"]) for r in starters]
        lu.bench = [Player(r["number"], r["name"], "bench", r["captain"]) for r in bench]
        return lu

    m.lineup_home = _lineup(m.home_team, home_start, home_bench)
    m.lineup_away = _lineup(m.away_team, away_start, away_bench)

    events = _team_events(home_start + home_bench, "home") + \
             _team_events(away_start + away_bench, "away")
    events.sort(key=lambda e: _minute_key(e.minute))
    m.events = events

    # --- Trainer + Offizielle -----------------------------------------------
    coaches: list[str] = []
    for tb in soup.find_all("table"):
        if tb.find("table") is not None:
            continue
        for tr in tb.find_all("tr"):
            cells = [_cell(td) for td in tr.find_all("td")]
            for i, c in enumerate(cells):
                if c == "TR" and i + 1 < len(cells) and cells[i + 1]:
                    coaches.append(_strip_contact(cells[i + 1]))
    if coaches:
        m.lineup_home.coach = coaches[0]
    if len(coaches) > 1:
        m.lineup_away.coach = coaches[1]

    # Offizielle: Label-Zelle -> Folgezelle
    label_map = {"Schiedsrichter": "referee", "Assistent 1": "a1", "Assistent 2": "a2"}
    found: dict[str, str] = {}
    for tb in soup.find_all("table"):
        if tb.find("table") is not None:
            continue
        for tr in tb.find_all("tr"):
            cells = [_cell(td) for td in tr.find_all("td")]
            for i, c in enumerate(cells):
                if c in label_map and i + 1 < len(cells) and cells[i + 1]:
                    found.setdefault(label_map[c], _strip_contact(cells[i + 1]))
    if "referee" in found:
        m.referee = found["referee"]
    m.assistants = [found[k] for k in ("a1", "a2") if k in found]


# --------------------------------------------------------------------------- #
# PARSER  (Heuristik-Fallback, falls die Druck-Struktur fehlt)
# --------------------------------------------------------------------------- #

def parse_match(html: str, match_id: str) -> Match:
    m = Match(match_id=str(match_id), url=BASE_URL.format(id=match_id))

    # Bevorzugt: echte Druck-Struktur (eingebetteter Spielbericht).
    report = _extract_report_soup(html)
    if report is not None and report.find(class_="headlinecontent"):
        _parse_report(report, m)
        return m

    # Fallback: alte Heuristik auf dem rohen HTML.
    soup = BeautifulSoup(html, "html.parser")

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
        w.writerow(["match_id", "side", "team", "role", "number", "player", "captain", "coach"])
        for m in matches:
            for side, lu in (("home", m.lineup_home), ("away", m.lineup_away)):
                for p in lu.starters + lu.bench:
                    w.writerow([m.match_id, side, lu.name, p.role, p.number, p.name,
                                p.captain, lu.coach])

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
    out.add_argument("--solve-challenge", action=argparse.BooleanOptionalAction,
                     default=True,
                     help="Anubis-Bot-Schutz per Proof-of-Work loesen (Default: an). "
                          "Mit --no-solve-challenge nur erkennen statt loesen.")

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
            html = fetch(session, mid, args.timeout, args.retries, args.backoff,
                         solve=args.solve_challenge)
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
        except ChallengeError as exc:
            log.error("  Bot-Schutz aktiv bei %s: %s", mid, exc)
            matches.append(Match(match_id=str(mid), url=BASE_URL.format(id=mid),
                                 ok=False, error=f"bot challenge: {exc}"))
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
