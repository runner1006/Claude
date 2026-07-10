#!/usr/bin/env python3
"""MCP-Server fuer die OEFB-Datenbank (data/oefb.sqlite).

Fertige Scouting-Tools + generisches read-only SQL. Laeuft lokal per stdio
(Claude Code / Claude Desktop) und wird vom FastAPI-Server unter /mcp auch
remote angeboten (streamable HTTP).

Lokaler Start (uv holt Abhaengigkeiten automatisch):
    uv run --python 3.12 --with "mcp[cli]" oefb_mcp.py
"""
from __future__ import annotations

import json
import os
import re
import sqlite3

from mcp.server.fastmcp import FastMCP

try:  # Host-Check des Streamable-HTTP-Transports lockern (Auth macht der
    # Bearer-Token in server/app.py; hinter Render-Proxy stimmt der Host nie)
    from mcp.server.transport_security import TransportSecuritySettings
    _TS = {"transport_security": TransportSecuritySettings(
        enable_dns_rebinding_protection=False)}
except ImportError:  # aeltere SDK-Version ohne Host-Check
    _TS = {}

DB = os.environ.get("OEFB_DB", os.path.join(os.path.dirname(__file__), "data", "oefb.sqlite"))

mcp = FastMCP(
    "oefb",
    **_TS,
    instructions=(
        "Datenbank des österreichischen Fußballs (oefb.at-Scrape): 10.990+ Spiele "
        "(Bundesland-Landesligen, Regionalligen, Oberligen, ÖFB-Jugendligen U15/U16/U18, "
        "Saisonen ab 2023/24), 13.000+ Spieler mit Profil (Nationalität, Karriere), "
        "Plus-Minus-Ratings (RAPM: off/def/total/peak, Talent-Perzentile je Jahrgang; "
        "0=Durchschnitt, Einheit Tore/90, Perzentil 0=bester). "
        "Tabellen: matches, players, appearances, events, ratings, player_stats, "
        "player_clubs, achievements, View competitions, FTS players_fts."
    ),
)


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _rows(sql: str, args=(), limit: int | None = None) -> list[dict]:
    with _con() as con:
        cur = con.execute(sql, args)
        rows = cur.fetchmany(limit) if limit else cur.fetchall()
        return [dict(r) for r in rows]


@mcp.tool()
def search_players(name: str, birth_year: int | None = None,
                   nationality: str | None = None, limit: int = 20) -> str:
    """Spieler per Name suchen (FTS, Praefix erlaubt). Optional nach Jahrgang/Nationalität filtern."""
    match = " ".join(w + "*" for w in re.findall(r"\w+", name))
    sql = ("SELECT p.player_id, p.name, p.birth_year, p.nationality, p.club, "
           "r.total, r.peak, r.pct_talent, r.minutes "
           "FROM players_fts f JOIN players p ON p.player_id=f.player_id "
           "LEFT JOIN ratings r ON r.player_id=p.player_id WHERE players_fts MATCH ?")
    args: list = [match]
    if birth_year:
        sql += " AND p.birth_year=?"; args.append(birth_year)
    if nationality:
        sql += " AND p.nationality LIKE ?"; args.append(f"%{nationality}%")
    sql += " LIMIT ?"; args.append(min(limit, 100))
    return json.dumps(_rows(sql, args), ensure_ascii=False, default=str)


@mcp.tool()
def get_player(player_id: str) -> str:
    """Komplettes Spielerprofil: Stammdaten, Rating, Saison-Aggregate, letzte Einsätze,
    Karriere-Vereine und Saison-Historie (Kader/Platzierungen)."""
    out = {
        "player": _rows("SELECT * FROM players WHERE player_id=?", (player_id,)),
        "rating": _rows("SELECT * FROM ratings WHERE player_id=?", (player_id,)),
        "seasons": _rows(
            """SELECT m.season, a.team, m.competition, COUNT(*) games,
                      SUM(a.minutes) minutes, SUM(a.goals) goals
               FROM appearances a JOIN matches m USING(match_id)
               WHERE a.player_id=? GROUP BY 1,2,3 ORDER BY m.season DESC""", (player_id,)),
        "last_matches": _rows(
            """SELECT m.iso_date, m.competition, a.team, a.side, m.home_team,
                      m.away_team, m.score, a.minutes, a.goals
               FROM appearances a JOIN matches m USING(match_id)
               WHERE a.player_id=? ORDER BY m.iso_date DESC LIMIT 15""", (player_id,)),
        "clubs": _rows("SELECT club, from_ms, land FROM player_clubs WHERE player_id=? "
                       "ORDER BY from_ms DESC", (player_id,)),
        "achievements": _rows("SELECT saison, club, kategorie, platzierung FROM achievements "
                              "WHERE player_id=? ORDER BY saison DESC LIMIT 30", (player_id,)),
    }
    return json.dumps(out, ensure_ascii=False, default=str)


@mcp.tool()
def get_match(match_id: str) -> str:
    """Ein Spiel mit Aufstellungen (inkl. Minuten) und allen Events."""
    out = {
        "match": _rows("SELECT * FROM matches WHERE match_id=?", (match_id,)),
        "lineup": _rows("SELECT side, team, role, position, number, name, player_id, "
                        "minutes, on_min, off_min, captain, goals FROM appearances "
                        "WHERE match_id=? ORDER BY side, role DESC, number", (match_id,)),
        "events": _rows("SELECT type, minute, team, player, player_out, detail "
                        "FROM events WHERE match_id=? ORDER BY minute", (match_id,)),
    }
    return json.dumps(out, ensure_ascii=False, default=str)


@mcp.tool()
def query_matches(competition: str | None = None, season: str | None = None,
                  team: str | None = None, date_from: str | None = None,
                  date_to: str | None = None, limit: int = 50) -> str:
    """Spiele filtern nach Bewerb, Saison (z.B. '2025/26'), Team, Datum (ISO)."""
    sql = "SELECT match_id, iso_date, competition, season, home_team, away_team, score FROM matches WHERE 1=1"
    args: list = []
    if competition:
        sql += " AND competition LIKE ?"; args.append(f"%{competition}%")
    if season:
        sql += " AND season=?"; args.append(season)
    if team:
        sql += " AND (home_team LIKE ? OR away_team LIKE ?)"; args += [f"%{team}%"] * 2
    if date_from:
        sql += " AND iso_date>=?"; args.append(date_from)
    if date_to:
        sql += " AND iso_date<=?"; args.append(date_to)
    sql += " ORDER BY iso_date DESC LIMIT ?"; args.append(min(limit, 500))
    return json.dumps(_rows(sql, args), ensure_ascii=False, default=str)


@mcp.tool()
def top_ratings(birth_year: int | None = None, competition: str | None = None,
                metric: str = "total", min_minutes: int = 270, limit: int = 25) -> str:
    """Bestenliste nach Rating. metric: total|off|def|peak|pct_talent (pct_talent: aufsteigend)."""
    if metric not in ("total", "off", "def", "peak", "pct_talent"):
        return json.dumps({"error": "metric muss total|off|def|peak|pct_talent sein"})
    order = "ASC" if metric == "pct_talent" else "DESC"
    sql = (f"SELECT r.player_id, r.name, r.birth_year, r.teams, r.competitions, "
           f"r.minutes, r.off, r.def, r.total, r.peak, r.pct_talent "
           f"FROM ratings r WHERE r.minutes>=? AND r.{metric} IS NOT NULL")
    args: list = [min_minutes]
    if birth_year:
        sql += " AND r.birth_year=?"; args.append(birth_year)
    if competition:
        sql += " AND r.competitions LIKE ?"; args.append(f"%{competition}%")
    sql += f" ORDER BY r.{metric} {order} LIMIT ?"; args.append(min(limit, 200))
    return json.dumps(_rows(sql, args), ensure_ascii=False, default=str)


@mcp.tool()
def team_summary(team: str, season: str | None = None) -> str:
    """Team-Überblick: Spiele/Bilanz je Saison + Kader mit Minuten/Toren/Rating."""
    like = f"%{team}%"
    args: list = [like, like]
    ssql = ""
    if season:
        ssql = " AND m.season=?"
    res = {
        "record": _rows(
            f"""SELECT m.season, m.competition, COUNT(*) games,
                SUM(CASE WHEN (m.home_team LIKE ? AND m.score_home>m.score_away)
                          OR (m.away_team LIKE ? AND m.score_away>m.score_home) THEN 1 ELSE 0 END) wins
                FROM matches m WHERE (m.home_team LIKE ? OR m.away_team LIKE ?){ssql}
                GROUP BY 1,2 ORDER BY m.season DESC""",
            [like, like, like, like] + ([season] if season else [])),
        "squad": _rows(
            f"""SELECT a.player_id, a.name, p.birth_year, COUNT(*) games,
                SUM(a.minutes) minutes, SUM(a.goals) goals, r.total, r.pct_talent
                FROM appearances a
                JOIN matches m USING(match_id)
                LEFT JOIN players p ON p.player_id=a.player_id
                LEFT JOIN ratings r ON r.player_id=a.player_id
                WHERE a.team LIKE ?{ssql}
                GROUP BY a.player_id, a.name ORDER BY minutes DESC LIMIT 40""",
            [like] + ([season] if season else [])),
    }
    return json.dumps(res, ensure_ascii=False, default=str)


_FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|attach|pragma|vacuum|replace)\b", re.I)


@mcp.tool()
def run_sql(sql: str, limit: int = 200) -> str:
    """Beliebige read-only SELECT-Query (max. 200 Zeilen). Schema siehe Server-Beschreibung."""
    if _FORBIDDEN.search(sql) or not re.match(r"\s*(select|with)\b", sql, re.I):
        return json.dumps({"error": "Nur SELECT/WITH-Queries erlaubt."})
    try:
        return json.dumps(_rows(sql, (), limit=min(limit, 1000)), ensure_ascii=False, default=str)
    except sqlite3.Error as e:
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
    mcp.run()
