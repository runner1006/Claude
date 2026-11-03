#!/usr/bin/env python3
"""Vorberechnete Dashboard-Daten: schnelles Laden statt ~180 MB Rohdaten im Browser.

Liest data/oefb.sqlite (nach build_db.py), data/matches.json (Trainer) und
data/players_profiles.json (Geburtsdatum -> exaktes Alter) und erzeugt:

  data/scout.json(.gz)          1 Zeile je Spieler: Aggregat aller Einsaetze + Rating
                                (Spalten in "cols"; teams/comps = Indizes in "teams"/
                                "competitions", zuletzt gespielt zuerst)
  data/matches_index.json(.gz)  1 Zeile je Spiel, ohne Aufstellungen/Events (comp/home/away
                                = Indizes in "competitions"/"teams")
  Tabelle dash_profile          fertiges Profil-JSON (gzip) je Spieler: alle Einsaetze
      in oefb.sqlite            mit rohem +/-, Jahrgangs-Referenzlinien (Top-20 %/Median),
                                Minuten-Split-Vergleich, Rating-Perzentile, Vereins- und
                                Saison-Historie
  Tabelle dash_meta             built, version, Zaehler

Die Rechenlogik entspricht 1:1 der bisherigen Browser-Berechnung in dashboard.html
(rawPM, playerGames, cohortSeries/cohortValsAt, quantile, cohortMinSplit, ratBench).

Aufruf: python build_dashboard.py [--data data] [--ref-date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import gzip
import json
import math
import os
import re
import sqlite3
import sys
from collections import defaultdict

import numpy as np

VERSION = 1
MINM = 270      # Mindestminuten fuer Rating-Benchmark und Kohorten-Referenz
COHMIN = 20     # Mindestanzahl Kohorten-Spieler fuer Referenzlinien


def log(*a):
    print(*a, file=sys.stderr, flush=True)


_JUGEND = re.compile(r"\bU\s?\d|jugend", re.I)


def league_cat(comp: str | None) -> str:
    return "Jugend" if _JUGEND.search(comp or "") else "Erwachsen"


_INT = re.compile(r"^\s*([+-]?\d+)")


def parse_int_js(s) -> int | None:
    """Wie parseInt(s,10) im Browser: fuehrende Ganzzahl, sonst None ("90+2" -> 90)."""
    m = _INT.match("" if s is None else str(s))
    return int(m.group(1)) if m else None


def age_on(birthdate_iso: str | None, ref: dt.date) -> int | None:
    if not birthdate_iso:
        return None
    try:
        b = dt.date.fromisoformat(birthdate_iso[:10])
    except ValueError:
        return None
    return ref.year - b.year - ((ref.month, ref.day) < (b.month, b.day))


def quantile_js(v: np.ndarray, q: float) -> float | None:
    """quantile() aus dashboard.html: lineare Interpolation auf sortierten Werten."""
    n = len(v)
    if n == 0:
        return None
    idx = (n - 1) * q
    lo, hi = math.floor(idx), math.ceil(idx)
    return float(v[lo] + (v[hi] - v[lo]) * (idx - lo))


def pct_in(sorted_vals: np.ndarray, x: float) -> float | None:
    """pctIn(): Anteil der Werte > x in Prozent (0 = bester)."""
    n = len(sorted_vals)
    if n == 0:
        return None
    lo = int(np.searchsorted(sorted_vals, x, side="right"))
    return 100.0 * (n - lo) / n


def r3(x):
    return None if x is None else round(float(x), 4)


# --------------------------------------------------------------------------- Laden

def load_birthdates(profiles_path: str) -> dict[str, str]:
    """Geburtsdaten aus players_profiles.json; Regex-Scan (schnell, wenig RAM),
    Fallback auf vollstaendiges JSON-Laden."""
    out: dict[str, str] = {}
    if not os.path.exists(profiles_path):
        return out
    pat = re.compile(r'"(\d+)":\{"geburtsdatum":"(\d{4}-\d{2}-\d{2})')
    with open(profiles_path, encoding="utf-8") as f:
        for m in pat.finditer(f.read()):
            out[m.group(1)] = m.group(2)
    if len(out) < 1000:   # Format anders als erwartet -> sicherer Weg
        with open(profiles_path, encoding="utf-8") as f:
            prof = json.load(f)
        out = {pid: p.get("geburtsdatum") for pid, p in prof.items() if p.get("geburtsdatum")}
    return out


def load_coaches(matches_json: str) -> dict[str, tuple[str, str]]:
    if not os.path.exists(matches_json):
        return {}
    with open(matches_json, encoding="utf-8") as f:
        ms = json.load(f)
    out = {}
    for m in ms:
        lh, la = m.get("lineup_home") or {}, m.get("lineup_away") or {}
        ch = lh.get("coach") if isinstance(lh, dict) else None
        ca = la.get("coach") if isinstance(la, dict) else None
        if ch or ca:
            out[str(m.get("match_id"))] = (ch or "", ca or "")
    return out


# --------------------------------------------------------------------------- Build

def build(data_dir: str, ref: dt.date) -> None:
    db = os.path.join(data_dir, "oefb.sqlite")
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    built = dt.datetime.now().replace(microsecond=0).isoformat()

    # ---- Matches -------------------------------------------------------------
    M: dict[str, dict] = {}
    for r in con.execute("SELECT * FROM matches"):
        m = dict(r)
        m["sh"] = m["score_home"] or 0
        m["sa"] = m["score_away"] or 0
        M[m["match_id"]] = m
    log(f"matches: {len(M)}")

    # ---- Tor-Events (nur numerische Minute zaehlt, wie parseInt im Browser) -----
    GOALS: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for r in con.execute("SELECT match_id, minute_raw, team FROM events WHERE type='goal'"):
        mm = parse_int_js(r["minute_raw"])
        if mm is None:
            continue
        GOALS[r["match_id"]].append((mm, r["team"] or ""))
    NEV: dict[str, int] = {r[0]: r[1] for r in
                           con.execute("SELECT match_id, COUNT(*) FROM events GROUP BY 1")}

    def raw_pm(mid: str, side: str, on: int, off: int):
        m = M[mid]
        expected = m["sh"] + m["sa"]
        gf = ga = cnt = 0
        for mm, team in GOALS.get(mid, ()):
            cnt += 1
            if mm < on or mm > off:
                continue
            if team == side:
                gf += 1
            elif team in ("home", "away"):
                ga += 1
        if expected > 0 and cnt < expected:
            return None, None, None
        return gf, ga, gf - ga

    # ---- Spieler / Ratings -----------------------------------------------------
    P: dict[str, dict] = {r["player_id"]: dict(r) for r in con.execute("SELECT * FROM players")}
    R: dict[str, dict] = {r["player_id"]: dict(r) for r in con.execute("SELECT * FROM ratings")}
    bdates = load_birthdates(os.path.join(data_dir, "players_profiles.json"))
    log(f"players: {len(P)} | ratings: {len(R)} | Geburtsdaten: {len(bdates)}")

    # Rating-Benchmark (alle Spieler >= 270 Min.): sortierte Verteilungen
    bench_rows = [r for r in R.values() if (r["minutes"] or 0) >= MINM]
    BENCH = {k: np.sort(np.array([r[k] for r in bench_rows if r[k] is not None], dtype=float))
             for k in ("off", "def", "total", "peak")}
    BENCH_N = len(bench_rows)

    # ---- Einsaetze -> Aggregat je Spieler + Spiele je Spieler --------------------
    agg: dict[str, dict] = {}
    games: dict[str, list[dict]] = defaultdict(list)
    n_app = 0
    n_skip = 0                      # Einsatzzeilen ohne zugehoeriges Spiel (sollte 0 sein)
    for r in con.execute("SELECT match_id, player_id, name, side, team, role, position, "
                         "minutes, on_min, off_min, captain, goals FROM appearances ORDER BY rowid"):
        n_app += 1
        mid = r["match_id"]
        m = M.get(mid)
        if m is None:
            n_skip += 1
            continue
        pid = r["player_id"] or ""
        key = pid or f"name::{r['name']}|{r['team']}"
        comp = m["competition"] or ""
        a = agg.get(key)
        if a is None:
            a = agg[key] = {"id": pid, "name": r["name"], "teams": {}, "comps": {},
                            "pos": {}, "role": r["role"] or "", "cap": False,
                            "min": 0, "matches": 0, "goals": 0, "first": None, "last": None}
        a["matches"] += 1
        a["min"] += r["minutes"] or 0
        a["goals"] += r["goals"] or 0
        if r["captain"]:
            a["cap"] = True
        if r["role"] == "starter":
            a["role"] = "starter"
        if r["position"]:
            a["pos"][r["position"]] = a["pos"].get(r["position"], 0) + 1
        iso = m["iso_date"] or ""
        for dkey, val in (("teams", r["team"]), ("comps", comp)):
            if val:
                prev = a[dkey].get(val)
                if prev is None or iso > prev:
                    a[dkey][val] = iso          # letztes Auftreten je Team/Bewerb
        if iso:
            a["first"] = iso if a["first"] is None or iso < a["first"] else a["first"]
            a["last"] = iso if a["last"] is None or iso > a["last"] else a["last"]

        mins = r["minutes"] or 0
        if not pid or mins <= 0:
            continue
        on = r["on_min"] or 0
        off = 90 if r["off_min"] is None else r["off_min"]
        gf, ga, pm = raw_pm(mid, r["side"], on, off)
        sh, sa = m["sh"], m["sa"]
        sf, sg = (sh, sa) if r["side"] == "home" else (sa, sh)
        games[pid].append({
            "mid": mid, "iso": iso, "date": m["date"] or "", "season": m["season"] or "?",
            "comp": comp, "cat": "J" if league_cat(comp) == "Jugend" else "E",
            "team": r["team"], "opp": m["away_team"] if r["side"] == "home" else m["home_team"],
            "ha": "H" if r["side"] == "home" else "A", "score": m["score"] or "",
            "sf": sf, "sg": sg, "res": "S" if sf > sg else ("N" if sf < sg else "U"),
            "min": mins, "on": on, "off": r["off_min"], "goals": r["goals"] or 0,
            "gf": gf, "ga": ga, "pm": pm, "pos": r["position"], "role": r["role"],
        })
    for g in games.values():
        g.sort(key=lambda x: x["iso"])      # stabil, wie im Browser
    log(f"appearances: {n_app} | Spieler-Aggregate: {len(agg)} | Spieler mit Einsatz: {len(games)}"
        + (f" | WARNUNG: {n_skip} Einsatzzeilen ohne Spiel uebersprungen" if n_skip else ""))

    # ---- scout.json --------------------------------------------------------------
    cols = ["id", "name", "teams", "comps", "by", "age", "pos", "role", "nat", "verband",
            "cap", "min", "matches", "goals", "first", "last",
            "off", "def", "total", "peak", "pct_talent", "pct_total", "pct_peak",
            "r_min", "r_matches"]
    rows = []
    for key, a in agg.items():
        p = P.get(a["id"]) or {}
        rt = R.get(a["id"])
        pos = max(a["pos"].items(), key=lambda kv: kv[1])[0] if a["pos"] else ""
        teams = [t for t, _ in sorted(a["teams"].items(), key=lambda kv: kv[1], reverse=True)]
        comps = [c for c, _ in sorted(a["comps"].items(), key=lambda kv: kv[1], reverse=True)]
        by = p.get("birth_year")
        age = age_on(bdates.get(a["id"]), ref)
        if age is None and by:
            age = ref.year - int(by)
        rows.append([a["id"], a["name"], teams, comps, by, age, pos, a["role"],
                     p.get("nationality") or "", p.get("verband") or "", a["cap"],
                     a["min"], a["matches"], a["goals"], a["first"], a["last"],
                     r3(rt["off"]) if rt else None, r3(rt["def"]) if rt else None,
                     r3(rt["total"]) if rt else None, r3(rt["peak"]) if rt else None,
                     r3(rt["pct_talent"]) if rt else None, r3(rt["pct_total"]) if rt else None,
                     r3(rt["pct_peak"]) if rt else None,
                     rt["minutes"] if rt else None, rt["matches"] if rt else None])
    # Team-/Bewerbsnamen als Woerterbuch (Index statt wiederholter Strings -> ~40 % kleiner)
    team_names = sorted({t for r in rows for t in r[2]}, key=str.casefold)
    comp_names = sorted({c for r in rows for c in r[3]}, key=str.casefold)
    tix = {t: i for i, t in enumerate(team_names)}
    cix = {c: i for i, c in enumerate(comp_names)}
    for r in rows:
        r[2] = [tix[t] for t in r[2]]
        r[3] = [cix[c] for c in r[3]]
    scout = {"v": VERSION, "built": built, "ref_date": ref.isoformat(),
             "stats": {"players": len(rows), "matches": len(M), "appearances": n_app,
                       "ratings": len(R), "bench_n": BENCH_N,
                       "latest_match": max((m["iso_date"] or "" for m in M.values()), default=None)},
             "teams": team_names, "competitions": comp_names, "cols": cols, "rows": rows}
    write_json(os.path.join(data_dir, "scout.json"), scout)

    # ---- matches_index.json ------------------------------------------------------
    coaches = load_coaches(os.path.join(data_dir, "matches.json"))
    mcols = ["id", "iso", "date", "time", "comp", "season", "round", "home", "away", "score",
             "sh", "sa", "ht", "venue", "spect", "ref", "nev", "coach_h", "coach_a", "url"]
    mteams = sorted({t for m in M.values() for t in (m["home_team"], m["away_team"]) if t}, key=str.casefold)
    mcomps = sorted({m["competition"] for m in M.values() if m["competition"]}, key=str.casefold)
    mtix = {t: i for i, t in enumerate(mteams)}
    mcix = {c: i for i, c in enumerate(mcomps)}
    mrows = []
    for m in sorted(M.values(), key=lambda x: (x["iso_date"] or "", x["match_id"])):
        if not m["iso_date"] and not m["home_team"]:
            continue                      # leere Spielberichte (ohne Datum/Teams) nicht listen
        ch, ca = coaches.get(m["match_id"], ("", ""))
        mrows.append([m["match_id"], m["iso_date"], m["date"], m["time"],
                      mcix.get(m["competition"]), m["season"], m["round"],
                      mtix.get(m["home_team"]), mtix.get(m["away_team"]), m["score"],
                      m["score_home"], m["score_away"], m["halftime"],
                      None if m["venue"] in (None, "None", "") else m["venue"],
                      m["spectators"], m["referee"], NEV.get(m["match_id"], 0), ch, ca, m["url"]])
    write_json(os.path.join(data_dir, "matches_index.json"),
               {"v": VERSION, "built": built, "teams": mteams, "competitions": mcomps,
                "cols": mcols, "rows": mrows})

    # ---- Kohorten je Jahrgang (Serien + Snapshots) --------------------------------
    by_players: dict[int, list[str]] = defaultdict(list)
    for pid in games:
        by = (P.get(pid) or {}).get("birth_year")
        if by:
            by_players[int(by)].append(pid)

    class Cohort:
        __slots__ = ("days", "snaps", "split")

    cohorts: dict[tuple[int, str], Cohort] = {}
    splits: dict[int, list[tuple[int, int, int]]] = {}
    for by, pids in by_players.items():
        sp = []
        for pid in pids:
            j = e = g = 0
            for gm in games[pid]:
                if gm["cat"] == "J":
                    j += gm["min"]
                else:
                    e += gm["min"]
                g += 1
            sp.append((j, e, g))
        splits[by] = sp
        for cat in ("J", "E"):
            series = []
            for pid in pids:
                cm = cp = 0
                arr = []
                for gm in games[pid]:
                    if gm["pm"] is None or gm["cat"] != cat:
                        continue
                    cm += gm["min"]
                    cp += gm["pm"]
                    arr.append((gm["iso"], cm, cp / cm * 90 if cm else 0.0))
                if arr:
                    series.append(arr)
            pts = [(d, si, cm, v) for si, ser in enumerate(series) for (d, cm, v) in ser]
            pts.sort(key=lambda t: t[0])
            S = len(series)
            cur = np.zeros(S)
            curmin = np.zeros(S, dtype=np.int64)
            c = Cohort()
            c.days, c.snaps, c.split = [], [], sp
            i = 0
            while i < len(pts):
                d = pts[i][0]
                while i < len(pts) and pts[i][0] == d:
                    _, si, cm, v = pts[i]
                    cur[si] = v
                    curmin[si] = cm
                    i += 1
                c.days.append(d)
                c.snaps.append(np.sort(cur[curmin >= MINM]))
            cohorts[(by, cat)] = c
    log(f"Kohorten: {len(by_players)} Jahrgaenge")

    def vals_at(by: int, cat: str, iso: str) -> np.ndarray:
        c = cohorts.get((by, cat))
        if c is None:
            return np.empty(0)
        k = bisect.bisect_right(c.days, iso) - 1
        return c.snaps[k] if k >= 0 else np.empty(0)

    # ---- Vereins-/Saison-Historie -----------------------------------------------
    clubs: dict[str, list] = defaultdict(list)
    for r in con.execute("SELECT player_id, club, from_ms, land FROM player_clubs ORDER BY rowid"):
        clubs[r["player_id"]].append([r["club"], r["from_ms"], r["land"]])
    achv: dict[str, list] = defaultdict(list)
    for r in con.execute("SELECT player_id, saison, club, kategorie, platzierung FROM achievements ORDER BY rowid"):
        achv[r["player_id"]].append([r["saison"], r["club"], r["kategorie"], r["platzierung"]])

    # ---- Profile ----------------------------------------------------------------
    con.executescript("""
        CREATE TABLE IF NOT EXISTS dash_profile(player_id TEXT PRIMARY KEY, gz BLOB);
        CREATE TABLE IF NOT EXISTS dash_meta(k TEXT PRIMARY KEY, v TEXT);
        DELETE FROM dash_profile; DELETE FROM dash_meta;
    """)
    n_prof = 0
    batch = []
    for pid, p in P.items():
        gs = games.get(pid, [])
        rt = R.get(pid)
        by = p.get("birth_year")
        by = int(by) if by else None
        min_j = sum(g["min"] for g in gs if g["cat"] == "J")
        min_e = sum(g["min"] for g in gs if g["cat"] == "E")
        tot = min_j + min_e
        dom = (("E" if min_e >= min_j else "J") if tot > 0 else None)
        vg = [g for g in gs if g["pm"] is not None]

        cohort: dict = {"by": by, "cat": dom, "ok": False, "th": [], "med": [], "pct": None, "n": 0}
        if by and dom and len(vg) >= 2:
            th, med = [], []
            ok = False
            for g in vg:
                vals = vals_at(by, dom, g["iso"])
                if len(vals) >= COHMIN:
                    ok = True
                    th.append(r3(quantile_js(vals, 0.8)))
                    med.append(r3(quantile_js(vals, 0.5)))
                else:
                    th.append(None)
                    med.append(None)
            cohort.update({"ok": ok, "th": th, "med": med})
            if ok:
                cm = sum(g["min"] for g in vg)
                cp = sum(g["pm"] for g in vg)
                fv = cp / cm * 90 if cm else 0.0
                vals = vals_at(by, dom, vg[-1]["iso"])
                cohort["n"] = int(len(vals))
                if len(vals) >= COHMIN:
                    cohort["pct"] = r3(100.0 * float((vals > fv).sum()) / len(vals))

        split = None
        sp = splits.get(by) if by else None
        if sp and len(sp) >= COHMIN:
            n = len(sp)
            split = {"n": n,
                     "e_fewer": r3(100.0 * sum(1 for j, e, g in sp if e < min_e) / n) if min_e > 0 else None,
                     "e_zero": r3(100.0 * sum(1 for j, e, g in sp if e == 0) / n) if min_e == 0 else None,
                     "j_fewer": r3(100.0 * sum(1 for j, e, g in sp if j < min_j) / n),
                     "avg_games": r3(sum(g for j, e, g in sp) / n)}

        bench = None
        if rt:
            bench = {"n": BENCH_N}
            for k in ("off", "def", "total", "peak"):
                bench[k] = r3(pct_in(BENCH[k], rt[k])) if rt[k] is not None else None

        age = age_on(bdates.get(pid), ref)
        if age is None and by:
            age = ref.year - by
        prof = {
            "v": VERSION, "built": built,
            "player": {"id": pid, "name": p["name"], "birth_year": by, "age": age,
                       "nationality": p["nationality"], "verband": p["verband"],
                       "club": p["club"], "foto_url": p["foto_url"], "youth": p["youth"],
                       "first_match": p["first_match"], "last_match": p["last_match"],
                       "n_clubs": p["n_clubs"],
                       "career": {"games": p["career_games"], "goals": p["career_goals"],
                                  "minutes": p["career_minutes"], "yellow": p["career_yellow"],
                                  "yellowred": p["career_yellowred"], "red": p["career_red"]}},
            "rating": ({k: rt[k] for k in ("off", "def", "total", "peak", "pct_total",
                                           "pct_peak", "pct_talent", "minutes", "matches",
                                           "teams", "competitions")} if rt else None),
            "bench": bench,
            "games": gs,
            "cohort": cohort,
            "split": split,
            "clubs": clubs.get(pid, []),
            "achievements": achv.get(pid, []),
        }
        blob = gzip.compress(json.dumps(prof, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 6)
        batch.append((pid, blob))
        n_prof += 1
        if len(batch) >= 500:
            con.executemany("INSERT INTO dash_profile VALUES(?,?)", batch)
            batch = []
    if batch:
        con.executemany("INSERT INTO dash_profile VALUES(?,?)", batch)
    con.executemany("INSERT INTO dash_meta VALUES(?,?)", [
        ("built", built), ("version", str(VERSION)), ("ref_date", ref.isoformat()),
        ("profiles", str(n_prof)), ("players", str(len(rows))), ("matches", str(len(M))),
        ("bench_n", str(BENCH_N))])
    con.commit()
    con.close()
    log(f"dash_profile: {n_prof} Profile -> {db} ({os.path.getsize(db)/1e6:.1f} MB)")
    log("FERTIG build_dashboard")


def write_json(path: str, obj) -> None:
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    with gzip.open(path + ".gz.tmp", "wb", compresslevel=6) as f:
        f.write(data)
    os.replace(path + ".gz.tmp", path + ".gz")
    log(f"{os.path.basename(path)}: {len(data)/1e6:.2f} MB, gz {os.path.getsize(path+'.gz')/1e6:.2f} MB")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", default="data")
    p.add_argument("--ref-date", metavar="YYYY-MM-DD",
                   help="Stichtag fuer die Altersberechnung (Default: heute)")
    args = p.parse_args(argv)
    ref = dt.date.fromisoformat(args.ref_date) if args.ref_date else dt.date.today()
    build(args.data, ref)
    return 0


if __name__ == "__main__":
    sys.exit(main())
