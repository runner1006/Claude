#!/usr/bin/env python3
"""
OEFB Spieler-Profile & -Alter
=============================

Ermittelt fuer jedes Spiel alle eingesetzten/gelisteten Spieler samt Alter,
Spielminuten UND vollem Spielerprofil und schreibt sie als CSV (eine Zeile pro
Spieler/Spiel). Zusaetzlich werden die reichen Profil-Rohdaten je Spieler nach
players_profiles.json geschrieben (Karriere-Vereine, Statistik je Kategorie,
Erfolge, Bewerbe).

Datenquellen
------------
1. Spielbericht (NICHT die Druckansicht):
       https://www.oefb.at/bewerbe/Spiel/Spielbericht/<SPIEL_ID>/
   enthaelt ein strukturiertes JSON (appPreloads) mit den Aufstellungen
   `heimAufstellung`/`gastAufstellung` – pro Spieler u.a. `rueckennummer`,
   `name`, `kapitaen` und `url` (-> /Profile/Spieler/<SPIELER_ID>).
2. Spielerprofil:
       https://www.oefb.at/Profile/Spieler/<SPIELER_ID>
   enthaelt ein appPreloads-Objekt mit `geburtsdatum`, `nationalitaet`,
   `verbandsKuerzel`, `verein`, `groesse`/`gewicht`, `nachwuchs`, `foto`,
   `erstesSpiel`/`letztesSpiel`, `vereine` (Karriere), `statistiken`
   (je Kategorie) und – separat – `erfolge`. All das wird via `parse_profile`
   extrahiert; skalare Felder landen im CSV (siehe CSV_PROFILE_FIELDS), die
   verschachtelten Rohdaten in players_profiles.json.

WICHTIG: Die oeffentlichen Profile geben aus Datenschutzgruenden nur das
GEBURTSJAHR preis (intern als 1. Januar gespeichert), nicht den genauen Tag.
Das Alter ist daher jahresbasiert und auf +-1 Jahr genau (Spalte `age` =
Stichtagsjahr - Geburtsjahr). `nationalitaet` ist nur befuellt, wenn oeffentlich
hinterlegt (oft, aber nicht immer – sonst leer). `groesse`/`gewicht` sind im
Nachwuchsbereich meist 0 (-> leer).

Die Anubis-Bot-Schutz-Challenge wird automatisch geloest (via oefb_scraper).
Die vollen Profile werden in einer Cache-Datei zwischengespeichert, damit
Profile ueber mehrere Laeufe hinweg nicht erneut geladen werden.

Beispiele
---------
    python player_ages.py --ids 3839515 -o data/players.csv
    python player_ages.py --ids-file data/all_ids.txt -o data/players.csv \\
           --cache data/profiles_cache.json --delay 0.5
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import time
import unicodedata

import requests

import oefb_scraper as oefb

# Regulaere Spieldauer (Minuten). Nachspielzeit weist OEFB im Druck/Bericht
# nicht aus; das Spielende wird auf 90' angenommen.
FULLTIME = 90


def _norm(s: str) -> str:
    """Akzent-/Gross-/Kleinschreibungs-unempfindlicher Namensschluessel."""
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()

REPORT_URL = "https://www.oefb.at/bewerbe/Spiel/Spielbericht/{id}/"
PROFILE_URL = "https://www.oefb.at/Profile/Spieler/{id}"

# Positionsgruppen in der Aufstellung; `ersatz` = Bank, alles andere = Startelf.
_GROUPS = ("tor", "abwehr", "mittelfeld", "sturm", "weitere", "ersatz")
_PROFILE_ID_RE = re.compile(r"/Profile/Spieler/(\d+)")
_GEBURT_RE = re.compile(r'"geburtsdatum"\s*:\s*(\d+)')

# Personen-Fotos liegen unter dieser Basis; die konkrete URL steht im
# `content="..."`-Meta-Tag und enthaelt den `foto`-Hash des Spielers.
_PERSON_IMG_BASE = "https://www.oefb.at/bewerbe/oefb2/person/images/"

# Statistik-Kennzahlen, die ueber alle Kategorie-Zeilen zu Karrieresummen
# aufaddiert werden (Spalte -> `karriere_<key>` im CSV).
_STAT_SUM_KEYS = ("spiele", "tore", "einsatzminuten", "siege", "unentschieden",
                  "niederlagen", "gelbe", "gelbrote", "rote")

# Kernfelder je Statistik-Zeile, die in players_profiles.json behalten werden.
# (Die OEFB-Rohzeile hat 44 Felder; die redundanten Bewerb-/Freundschaft-Splits
#  werden verworfen, um die Datei klein zu halten.)
_STAT_KEEP_KEYS = ("kategorie", "bezeichnung", "spiele", "tore", "siege",
                   "unentschieden", "niederlagen", "einsatzminuten",
                   "minutenProSpiel", "toreProSpiel", "einwechslungen",
                   "auswechslungen", "gelbe", "gelbrote", "rote")

# Skalare Profil-Spalten, die zusaetzlich in players.csv geschrieben werden.
# (Die verschachtelten Daten – Karriere-Vereine, Statistik-Zeilen, Erfolge,
#  Bewerbe – landen nur in players_profiles.json, nicht im CSV.)
CSV_PROFILE_FIELDS = [
    "nationalitaet", "verband", "profil_verein", "groesse", "gewicht",
    "nachwuchs", "blueCards", "foto_url", "erstes_spiel", "letztes_spiel",
    "anzahl_vereine", "bewerbe_aktuell",
    "karriere_spiele", "karriere_tore", "karriere_minuten", "karriere_siege",
    "karriere_unentschieden", "karriere_niederlagen",
    "karriere_gelbe", "karriere_gelbrote", "karriere_rote",
]

log = oefb.log


def _iso_from_ms(ms) -> str | None:
    """ISO-Datum aus einem OEFB-Millisekunden-Timestamp (lokale Mitternacht).

    Wie bei den Geburtsdaten wird +12h addiert, damit die Umrechnung
    zeitzonenunabhaengig auf den richtigen Kalendertag faellt. <=0 -> None.
    """
    if not isinstance(ms, (int, float)) or ms <= 0:
        return None
    secs = ms / 1000 + 12 * 3600
    return dt.datetime.utcfromtimestamp(secs).date().isoformat()


def _preload_dicts(html: str) -> list[dict]:
    """Alle Dict-Objekte aus den appPreloads-Arrays der Seite."""
    dec = json.JSONDecoder()
    out: list[dict] = []
    for m in re.finditer(r"appPreloads\['?-?\d+'?\]\s*=\s*", html):
        start = html.find("[", m.end())
        if start == -1:
            continue
        try:
            arr, _ = dec.raw_decode(html, start)
        except ValueError:
            continue
        out.extend(x for x in arr if isinstance(x, dict))
    return out


def parse_profile(html: str) -> dict | None:
    """Extrahiert das komplette Spielerprofil aus einer /Profile/Spieler-Seite.

    Liefert ein normalisiertes Dict mit skalaren Feldern (fuers CSV) und den
    verschachtelten Rohdaten (Karriere-Vereine, Statistik-Zeilen, Erfolge,
    Bewerbe – fuer players_profiles.json). None, wenn kein Profil gefunden.
    """
    dicts = _preload_dicts(html)
    p = next((d for d in dicts if "nationalitaet" in d), None)
    if p is None:
        return None
    # Erfolge liegen in einem separaten Preload-Objekt (ohne `nationalitaet`).
    erf_obj = next((d for d in dicts
                    if "erfolge" in d and "nationalitaet" not in d), None)
    erfolge = (erf_obj or {}).get("erfolge") or []

    raw_stats = p.get("statistiken") or []
    totals = {k: 0 for k in _STAT_SUM_KEYS}
    for s in raw_stats:
        for k in _STAT_SUM_KEYS:
            v = s.get(k)
            if isinstance(v, (int, float)):
                totals[k] += int(v)
    # auf Kernfelder abschlanken (siehe _STAT_KEEP_KEYS)
    stats = [{k: s.get(k) for k in _STAT_KEEP_KEYS} for s in raw_stats]

    # Foto-URL: bevorzugt die content=-URL, die den foto-Hash des Spielers
    # enthaelt (schliesst fremde Personenbilder auf der Seite aus).
    foto_url = None
    fhash = p.get("foto")
    if fhash:
        m = re.search(r'content="(' + re.escape(_PERSON_IMG_BASE)
                      + r'[^"]*' + re.escape(fhash) + r'[^"]*)"', html)
        foto_url = m.group(1) if m else None

    geb = _iso_from_ms(p.get("geburtsdatum"))
    return {
        # --- skalare Felder (auch im CSV) ---
        "geburtsdatum": geb,
        "birth_year": int(geb[:4]) if geb else None,
        "nationalitaet": p.get("nationalitaet") or None,
        "verband": p.get("verbandsKuerzel") or None,
        "profil_verein": p.get("verein") or None,
        "verein_id": p.get("vereinId") or None,
        "verein_logo": p.get("vereinLogo") or None,
        "groesse": p.get("groesse") or None,   # 0 -> None (im Nachwuchs oft leer)
        "gewicht": p.get("gewicht") or None,
        "nachwuchs": bool(p.get("nachwuchs")),
        "blueCards": int(p.get("blueCards") or 0),
        "titel": p.get("titel") or None,
        "foto_url": foto_url,
        "erstes_spiel": _iso_from_ms((p.get("erstesSpiel") or {}).get("datum")),
        "letztes_spiel": _iso_from_ms((p.get("letztesSpiel") or {}).get("datum")),
        "anzahl_vereine": len(p.get("vereine") or []),
        "bewerbe_aktuell": "; ".join(
            b.get("name", "") for b in (p.get("bewerbe") or []) if b.get("name")),
        "karriere_spiele": totals["spiele"],
        "karriere_tore": totals["tore"],
        "karriere_minuten": totals["einsatzminuten"],
        "karriere_siege": totals["siege"],
        "karriere_unentschieden": totals["unentschieden"],
        "karriere_niederlagen": totals["niederlagen"],
        "karriere_gelbe": totals["gelbe"],
        "karriere_gelbrote": totals["gelbrote"],
        "karriere_rote": totals["rote"],
        # --- verschachtelte Rohdaten (nur players_profiles.json) ---
        "vorname": p.get("vorname"),
        "nachname": p.get("nachname"),
        "vereine": p.get("vereine") or [],
        "statistiken": stats,
        "erfolge": erfolge,
        "bewerbe": p.get("bewerbe") or [],
        "erstesSpiel": p.get("erstesSpiel"),
        "letztesSpiel": p.get("letztesSpiel"),
    }


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


def _find_match_data(html: str) -> dict | None:
    """Holt das appPreloads-Objekt mit den Aufstellungen aus der Spielberichtseite."""
    dec = json.JSONDecoder()
    for m in re.finditer(r"appPreloads\['?-?\d+'?\]\s*=\s*", html):
        start = html.find("[", m.end())
        if start == -1:
            continue
        try:
            arr, _ = dec.raw_decode(html, start)
        except ValueError:
            continue
        for item in arr:
            if isinstance(item, dict) and "heimAufstellung" in item:
                return item
    return None


def _players_from_lineup(auf: dict, side: str) -> list[dict]:
    """Flacht eine Aufstellung (`heim`/`gast`) zu Spieler-Dicts ab."""
    out: list[dict] = []
    team = auf.get("vereinName")
    for group in _GROUPS:
        for p in auf.get(group) or []:
            pid = _PROFILE_ID_RE.search(p.get("url") or "")
            out.append({
                "side": side,
                "team": team,
                "role": "bench" if group == "ersatz" else "starter",
                "position": group,
                "number": p.get("rueckennummer"),
                "name": p.get("name"),
                "player_id": pid.group(1) if pid else None,
                "captain": bool(p.get("kapitaen")),
                "goals": p.get("tore") or 0,
            })
    return out


def _real_minute(e: dict) -> int | None:
    """Echte Spielminute eines gameData-Events.

    `minuteString` ist die angezeigte Minute; `minute` ist intern um +15
    versetzt (Halbzeitpause), daher als Fallback minus 15.
    """
    ms = e.get("minuteString")
    if ms not in (None, ""):
        mm = re.match(r"\d+", str(ms))
        if mm:
            return int(mm.group())
    mn = e.get("minute")
    return int(mn) - 15 if isinstance(mn, (int, float)) else None


def _attach_minutes(players: list[dict], gamedata: list[dict] | None) -> None:
    """Berechnet je Spieler `minutes` (+ on/off) aus der Wechsel-/Karten-Timeline."""
    side_of = {"a": "home", "b": "away"}
    came_on: dict[tuple, int] = {}
    went_off: dict[tuple, int] = {}
    sent_off: dict[tuple, int] = {}
    for e in gamedata or []:
        t = e.get("type") or ""
        side = side_of.get(e.get("team"))
        rm = _real_minute(e)
        if side is None or rm is None:
            continue
        if t == "playerchange":
            if e.get("playerPrimary"):    # playerPrimary = eingewechselt
                came_on[(side, _norm(e["playerPrimary"]))] = rm
            if e.get("playerSecondary"):  # playerSecondary = ausgewechselt
                went_off[(side, _norm(e["playerSecondary"]))] = rm
        elif "red" in t:                  # rote / gelb-rote Karte -> Feld verlassen
            if e.get("playerPrimary"):
                sent_off[(side, _norm(e["playerPrimary"]))] = rm
    for pl in players:
        key = (pl["side"], _norm(pl["name"]))
        start = 0 if pl["role"] == "starter" else came_on.get(key)
        if start is None:                 # Bank ohne Einwechslung -> nicht gespielt
            pl.update(minutes=0, on=None, off=None, played=False)
            continue
        end = FULLTIME
        for tbl in (went_off, sent_off):
            if key in tbl:
                end = min(end, tbl[key])
        pl.update(minutes=max(0, end - start),
                  on=start,
                  off=end if (key in went_off or key in sent_off) else None,
                  played=True)


def match_players(session: requests.Session, match_id: str,
                  timeout: float = 30.0) -> tuple[str, list[dict]]:
    """Liefert (titel, spielerliste mit Minuten) fuer ein Spiel."""
    html = get(session, REPORT_URL.format(id=match_id), timeout)
    data = _find_match_data(html)
    if not data:
        raise RuntimeError(f"Keine Aufstellungsdaten fuer Spiel {match_id} gefunden.")
    players = (_players_from_lineup(data.get("heimAufstellung") or {}, "home") +
               _players_from_lineup(data.get("gastAufstellung") or {}, "away"))
    _attach_minutes(players, data.get("gameData"))
    return data.get("title", str(match_id)), players


def profile_of(session: requests.Session, player_id: str,
               cache: dict, timeout: float = 30.0, delay: float = 0.0) -> dict:
    """Vollstaendiges Spielerprofil (mit Cache). Leeres Dict, wenn kein Profil.

    Der Cache haelt je Spieler das komplette normalisierte Profil-Dict (inkl.
    Geburtsjahr, Nationalitaet, Verein, Karriere, Statistik, Erfolge ...),
    sodass ueber mehrere Laeufe hinweg kein Profil erneut geladen wird.
    """
    if player_id in cache:
        return cache[player_id]
    html = get(session, PROFILE_URL.format(id=player_id), timeout)
    prof = parse_profile(html) or {}
    cache[player_id] = prof
    if delay > 0:
        time.sleep(delay)
    return prof


def age_on(birthdate_iso: str | None, ref: dt.date) -> int | None:
    if not birthdate_iso:
        return None
    b = dt.date.fromisoformat(birthdate_iso)
    return ref.year - b.year - ((ref.month, ref.day) < (b.month, b.day))


def has_age(player_id: str | None, cache: dict) -> bool:
    """True, wenn fuer den Spieler bereits ein (Nicht-)Datum ermittelt wurde.

    Im Cache stehende `None`-Werte zaehlen als 'geprueft' (kein Datum
    hinterlegt) und werden daher NICHT erneut geladen.
    """
    return bool(player_id) and player_id in cache


def partition_ids(player_ids, cache: dict) -> tuple[list[str], list[str]]:
    """Teilt Spieler-IDs in (bereits_bekannt, neu_zu_laden) anhand des Caches.

    Damit laesst sich vor einem Lauf bestimmen, wessen Alter schon vorliegt –
    nur die 'neuen' muessen tatsaechlich vom Profil geladen werden.
    """
    seen: set[str] = set()
    known: list[str] = []
    new: list[str] = []
    for pid in player_ids:
        if not pid or pid in seen:
            continue
        seen.add(pid)
        (known if pid in cache else new).append(pid)
    return known, new


def load_cache(path: str | None) -> dict:
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def save_cache(path: str | None, cache: dict) -> None:
    if not path:
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=0)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Ermittelt das Alter jedes Spielers pro Spiel.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    src = p.add_argument_group("Spiel-IDs")
    src.add_argument("--ids", nargs="+", metavar="ID", help="Einzelne Spiel-IDs")
    src.add_argument("--ids-file", metavar="DATEI", help="Datei mit einer ID pro Zeile")
    p.add_argument("-o", "--out", default="players.csv", help="Ziel-CSV (Default: players.csv)")
    p.add_argument("--cache", default="data/profiles_cache.json",
                   help="Cache-Datei fuer die vollen Profile "
                        "(Default: data/profiles_cache.json)")
    p.add_argument("--profiles-json", default="data/players_profiles.json",
                   help="Ziel fuer die reichen Profil-Rohdaten je Spieler "
                        "(Default: data/players_profiles.json)")
    p.add_argument("--ref-date", metavar="YYYY-MM-DD",
                   help="Stichtag fuer die Altersberechnung (Default: heute)")
    p.add_argument("--delay", type=float, default=0.5,
                   help="Pause zwischen Profil-Abfragen in Sek. (Default: 0.5)")
    p.add_argument("--timeout", type=float, default=30.0)
    args = p.parse_args(argv)

    oefb.logging.basicConfig(level=oefb.logging.INFO,
                             format="%(asctime)s %(levelname)s %(message)s",
                             datefmt="%H:%M:%S")

    ids: list[str] = list(args.ids or [])
    if args.ids_file:
        ids += [l.strip() for l in open(args.ids_file, encoding="utf-8")
                if l.strip() and not l.startswith("#")]
    ids = list(dict.fromkeys(ids))
    if not ids:
        p.error("Keine IDs (--ids oder --ids-file).")

    ref = dt.date.fromisoformat(args.ref_date) if args.ref_date else dt.date.today()
    session = make_session()
    cache = load_cache(args.cache)
    log.info("%d Spiel(e), Stichtag %s, %d Profile im Cache.",
             len(ids), ref.isoformat(), len(cache))

    rows: list[dict] = []
    all_pids: set[str] = set()
    fetched = 0  # tatsaechlich neu vom Profil geladen
    for idx, mid in enumerate(ids, 1):
        try:
            title, players = match_players(session, mid, args.timeout)
        except Exception as exc:  # noqa: BLE001
            log.error("[%d/%d] Spiel %s: %s", idx, len(ids), mid, exc)
            continue
        for pl in players:
            prof: dict = {}
            if pl["player_id"]:
                all_pids.add(pl["player_id"])
                was_known = has_age(pl["player_id"], cache)  # vor dem Laden pruefen
                try:
                    prof = profile_of(session, pl["player_id"], cache,
                                      args.timeout, 0.0 if was_known else args.delay)
                    if not was_known:
                        fetched += 1
                except Exception as exc:  # noqa: BLE001
                    log.warning("  Profil %s fehlgeschlagen: %s", pl["player_id"], exc)
            pl["match_id"] = str(mid)
            # oeffentlich ist nur das Jahr bekannt (Datum = 1.1.) -> nur Jahr ausgeben
            pl["birth_year"] = prof.get("birth_year")
            pl["age"] = age_on(prof.get("geburtsdatum"), ref)
            for k in CSV_PROFILE_FIELDS:  # skalare Profil-Felder anhaengen
                pl[k] = prof.get(k)
            rows.append(pl)
        ages = [r["age"] for r in rows if r["match_id"] == str(mid) and r["age"] is not None]
        avg = f"{sum(ages)/len(ages):.1f}" if ages else "—"
        log.info("[%d/%d] %s: %d Spieler, Ø %s J. (neu geladen: %d)",
                 idx, len(ids), title, len(players), avg, fetched)
        save_cache(args.cache, cache)  # inkrementell sichern

    log.info("Spieler gesamt: %d | aus Cache: %d | neu geladen: %d",
             len(all_pids), len(all_pids) - fetched, fetched)

    fields = ["match_id", "side", "team", "role", "position", "number", "name",
              "player_id", "birth_year", "age", "minutes", "on", "off",
              "captain", "goals"] + CSV_PROFILE_FIELDS
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})

    # Reiche Profil-Rohdaten (Karriere, Statistik, Erfolge, Bewerbe) je Spieler,
    # der im Datensatz vorkommt -> players_profiles.json fuer Detailansichten.
    if args.profiles_json:
        profiles = {pid: cache[pid] for pid in sorted(all_pids)
                    if cache.get(pid)}
        with open(args.profiles_json, "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False, separators=(",", ":"))
        log.info("Profile-Rohdaten: %d Spieler -> %s",
                 len(profiles), args.profiles_json)

    log.info("Fertig. %d Spieler-Zeilen -> %s (Cache: %d Profile)",
             len(rows), args.out, len(cache))
    return 0


if __name__ == "__main__":
    sys.exit(main())
