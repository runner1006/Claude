#!/usr/bin/env python3
"""Baut die SQLite-Datenbank (data/oefb.sqlite) aus den Rohdaten.

Normalisiertes Schema: Profildaten stehen 1x je Spieler (statt in jeder
players.csv-Zeile wiederholt), Einsaetze/Events/Ratings in eigenen Tabellen,
FTS5-Index fuer die Namenssuche. Der Build schreibt in eine .tmp-Datei und
ersetzt die DB atomar -> idempotent und immer konsistent; als letzter
Pipeline-Schritt nach plusminus.py gedacht.

Aufruf: python build_db.py  [-o data/oefb.sqlite]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import sys

csv.field_size_limit(10_000_000)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def season_of(date_str: str) -> str | None:
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", date_str or "")
    if not m:
        return None
    mm, yy = int(m.group(2)), int(m.group(3))
    return f"{yy-1}/{str(yy)[2:]}" if mm < 7 else f"{yy}/{str(yy+1)[2:]}"


def iso_of(date_str: str) -> str | None:
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", date_str or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def _int(v, default=None):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


SCHEMA = """
CREATE TABLE matches(
  match_id TEXT PRIMARY KEY, competition TEXT, season TEXT, round TEXT,
  date TEXT, iso_date TEXT, time TEXT, venue TEXT, spectators INTEGER,
  referee TEXT, home_team TEXT, away_team TEXT,
  score TEXT, score_home INTEGER, score_away INTEGER, halftime TEXT, url TEXT);
CREATE TABLE players(
  player_id TEXT PRIMARY KEY, name TEXT, birth_year INTEGER, nationality TEXT,
  verband TEXT, club TEXT, foto_url TEXT, youth INTEGER,
  first_match TEXT, last_match TEXT, n_clubs INTEGER,
  career_games INTEGER, career_goals INTEGER, career_minutes INTEGER,
  career_yellow INTEGER, career_yellowred INTEGER, career_red INTEGER);
CREATE TABLE appearances(
  match_id TEXT, player_id TEXT, name TEXT, side TEXT, team TEXT,
  role TEXT, position TEXT, number TEXT,
  minutes INTEGER, on_min INTEGER, off_min INTEGER,
  captain INTEGER, goals INTEGER);
CREATE TABLE events(
  match_id TEXT, type TEXT, minute INTEGER, minute_raw TEXT, team TEXT,
  player TEXT, player_out TEXT, detail TEXT);
CREATE TABLE ratings(
  player_id TEXT PRIMARY KEY, name TEXT, birth_year INTEGER,
  teams TEXT, competitions TEXT, minutes INTEGER, matches INTEGER,
  off REAL, def REAL, total REAL, peak REAL,
  pct_total REAL, pct_peak REAL, pct_talent REAL);
CREATE TABLE player_stats(
  player_id TEXT, kategorie TEXT, bezeichnung TEXT,
  spiele INTEGER, tore INTEGER, siege INTEGER, unentschieden INTEGER,
  niederlagen INTEGER, einsatzminuten INTEGER, einwechslungen INTEGER,
  auswechslungen INTEGER, gelbe INTEGER, gelbrote INTEGER, rote INTEGER);
CREATE TABLE player_clubs(
  player_id TEXT, club TEXT, from_ms INTEGER, land TEXT);
CREATE TABLE achievements(
  player_id TEXT, saison TEXT, club TEXT, kategorie TEXT, platzierung TEXT);
CREATE VIRTUAL TABLE players_fts USING fts5(name, player_id UNINDEXED);
"""

INDEXES = """
CREATE INDEX idx_app_player ON appearances(player_id);
CREATE INDEX idx_app_match ON appearances(match_id);
CREATE INDEX idx_app_team ON appearances(team);
CREATE INDEX idx_matches_comp ON matches(competition, season);
CREATE INDEX idx_matches_iso ON matches(iso_date);
CREATE INDEX idx_events_match ON events(match_id);
CREATE INDEX idx_stats_player ON player_stats(player_id);
CREATE INDEX idx_clubs_player ON player_clubs(player_id);
CREATE INDEX idx_ach_player ON achievements(player_id);
CREATE INDEX idx_ratings_by ON ratings(birth_year);
CREATE VIEW competitions AS
  SELECT competition, season, COUNT(*) AS matches,
         MIN(iso_date) AS first_match, MAX(iso_date) AS last_match
  FROM matches GROUP BY competition, season;
"""


def build(data_dir: str, out: str) -> None:
    tmp = out + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)

    # --- matches ---
    with open(f"{data_dir}/matches.csv", encoding="utf-8") as f:
        rows = [(r["match_id"], r["competition"], season_of(r["date"]), r["round"],
                 r["date"], iso_of(r["date"]), r["time"], r["venue"],
                 _int(r["spectators"]), r["referee"], r["home_team"], r["away_team"],
                 r["score"], _int(r["score_home"]), _int(r["score_away"]),
                 r["halftime"], r["url"])
                for r in csv.DictReader(f) if (r.get("ok") or "").lower() == "true"]
    con.executemany("INSERT OR REPLACE INTO matches VALUES(" + ",".join("?"*17) + ")", rows)
    log(f"matches: {len(rows)}")

    # --- appearances + players (Profil 1x aus der ersten vollstaendigen Zeile) ---
    apps, players = [], {}
    with open(f"{data_dir}/players.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pid = r["player_id"] or None
            apps.append((r["match_id"], pid, r["name"], r["side"], r["team"],
                         r["role"], r["position"], r["number"],
                         _int(r["minutes"], 0), _int(r["on"]), _int(r["off"]),
                         1 if (r["captain"] or "").lower() == "true" else 0,
                         _int(r["goals"], 0)))
            if pid and pid not in players:
                players[pid] = (pid, r["name"], _int(r["birth_year"]),
                                r["nationalitaet"] or None, r["verband"] or None,
                                r["profil_verein"] or None, r["foto_url"] or None,
                                1 if (r["nachwuchs"] or "").lower() == "true" else 0,
                                r["erstes_spiel"] or None, r["letztes_spiel"] or None,
                                _int(r["anzahl_vereine"]),
                                _int(r["karriere_spiele"]), _int(r["karriere_tore"]),
                                _int(r["karriere_minuten"]), _int(r["karriere_gelbe"]),
                                _int(r["karriere_gelbrote"]), _int(r["karriere_rote"]))
    con.executemany("INSERT INTO appearances VALUES(" + ",".join("?"*13) + ")", apps)
    con.executemany("INSERT OR REPLACE INTO players VALUES(" + ",".join("?"*17) + ")",
                    players.values())
    log(f"appearances: {len(apps)} | players: {len(players)}")

    # --- events ---
    with open(f"{data_dir}/events.csv", encoding="utf-8") as f:
        evs = [(r["match_id"], r["type"], _int(r["minute"]), r["minute"], r["team"],
                r["player"], r["player_out"], r["detail"])
               for r in csv.DictReader(f)]
    con.executemany("INSERT INTO events VALUES(?,?,?,?,?,?,?,?)", evs)
    log(f"events: {len(evs)}")

    # --- ratings ---
    with open(f"{data_dir}/ratings.csv", encoding="utf-8") as f:
        def fl(v):
            try: return float(v)
            except (TypeError, ValueError): return None
        rats = [(r["player_id"], r["name"], _int(r["birth_year"]), r["teams"],
                 r["competitions"], _int(r["minutes"], 0), _int(r["matches"], 0),
                 fl(r["off"]), fl(r["def"]), fl(r["total"]), fl(r["peak"]),
                 fl(r["pct_total"]), fl(r["pct_peak"]), fl(r["pct_talent"]))
                for r in csv.DictReader(f)]
    con.executemany("INSERT OR REPLACE INTO ratings VALUES(" + ",".join("?"*14) + ")", rats)
    log(f"ratings: {len(rats)}")

    # --- Profil-Rohdaten: stats / clubs / achievements ---
    prof = json.load(open(f"{data_dir}/players_profiles.json", encoding="utf-8"))
    st, cl, ac = [], [], []
    for pid, p in prof.items():
        for s in p.get("statistiken") or []:
            st.append((pid, s.get("kategorie"), s.get("bezeichnung"),
                       _int(s.get("spiele"), 0), _int(s.get("tore"), 0),
                       _int(s.get("siege"), 0), _int(s.get("unentschieden"), 0),
                       _int(s.get("niederlagen"), 0), _int(s.get("einsatzminuten"), 0),
                       _int(s.get("einwechslungen"), 0), _int(s.get("auswechslungen"), 0),
                       _int(s.get("gelbe"), 0), _int(s.get("gelbrote"), 0),
                       _int(s.get("rote"), 0)))
        for c in p.get("vereine") or []:
            cl.append((pid, c.get("verein"), _int(c.get("ab")), c.get("landCode")))
        for e in p.get("erfolge") or []:
            ac.append((pid, e.get("saison"), e.get("verein"), e.get("kategorie"),
                       e.get("ziel")))
    con.executemany("INSERT INTO player_stats VALUES(" + ",".join("?"*14) + ")", st)
    con.executemany("INSERT INTO player_clubs VALUES(?,?,?,?)", cl)
    con.executemany("INSERT INTO achievements VALUES(?,?,?,?,?)", ac)
    log(f"player_stats: {len(st)} | player_clubs: {len(cl)} | achievements: {len(ac)}")

    # --- FTS + Indizes ---
    con.executemany("INSERT INTO players_fts(name, player_id) VALUES(?,?)",
                    [(p[1], p[0]) for p in players.values()])
    con.executescript(INDEXES)
    con.commit()
    con.execute("VACUUM")
    con.close()
    os.replace(tmp, out)
    log(f"FERTIG -> {out} ({os.path.getsize(out)/1e6:.1f} MB)")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", default="data")
    p.add_argument("-o", "--out", default="data/oefb.sqlite")
    args = p.parse_args(argv)
    build(args.data, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
