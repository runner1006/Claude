#!/usr/bin/env python3
"""
OEFB Plus-Minus-Ratings (RAPM)
==============================

Berechnet Regularized-Adjusted-Plus-Minus-Ratings (offensiv/defensiv/total)
fuer die gescrapten OEFB-Daten – nach der Methodik von Hvattum (2020) bzw.
Hvattum, Kriegl & Culik (2021), "Identifying talent in association football
through plus-minus ratings".

Idee
----
Jedes Spiel wird in *Segmente* zerlegt, in denen sich die Spieler auf dem Feld
nicht aendern (Grenzen: Ein-/Auswechslungen und Rote/Gelb-Rote Karten). Pro
Segment gilt naeherungsweise:

    Tore(Heim) ~ (Dauer/90) * ( const + HFA
                                + Σ offensiv(Heimspieler)
                                − Σ defensiv(Gastspieler)
                                + manvorteil * (n_heim − n_gast) )

und symmetrisch fuer die Gasttore (ohne HFA). Nach Ilardi (2007) erzeugt jedes
Segment ZWEI Beobachtungen (jede Mannschaft einmal in der Offensive). Die
Spieler-Ratings sind die Koeffizienten einer ridge-regularisierten
Kleinste-Quadrate-Schaetzung: Ratings werden gegen 0 (Durchschnitt) gezogen,
damit Spieler mit wenigen Minuten kein verrauschtes Rating bekommen.

Total = offensiv + defensiv. Das *Peak-Rating* projiziert das Total-Rating via
einer (fest hinterlegten, aus Fig. 1 des Papers digitalisierten) Alterskurve auf
das erwartete Leistungshoch – so werden junge und reife Spieler vergleichbar.

Datenquellen (aus dem Scraper)
------------------------------
- data/players.csv : eine Zeile je Spieler/Spiel mit `on`/`off`/`minutes`
                     (Praesenz-Intervall; Rote Karten sind in `off` bereits
                     beruecksichtigt), `side`, `team`, `player_id`, `birth_year`.
- data/events.csv  : Tore (`type=goal`, `minute`, `team`) je Spiel.
- data/matches.csv : Bewerb/competition je `match_id` (nur fuer die Ausgabe).

MVP-Hinweise / Grenzen
----------------------
- Nur EINE Saison => Ratings sind verrauscht; die Alterskurve wird NICHT
  geschaetzt, sondern fest uebernommen (Paper). Fuer robuste Werte mehr Saisons
  scrapen.
- Gewichte w(m,s) sind hier 1 (keine Aktualitaets-/Garbage-Time-Gewichtung).
- Eigentore/Elfmeter werden wie normale Tore der begünstigten Mannschaft gezaehlt.

Aufruf
------
    python plusminus.py                      # nutzt data/*.csv, schreibt data/ratings.csv
    python plusminus.py --lam 100 --no-cv    # festes Lambda ohne Cross-Validation
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import lsqr

FULLTIME = 90

# Alterskurve (Gesamt-Rating-Anpassung), approximativ aus Fig. 1 des Papers
# digitalisiert: Verbesserung bis ~22, Plateau bis Anfang 30, danach Abfall.
# Einheit = dieselbe wie die Ratings (Tore/90). Leicht ersetzbar.
_AGE_CURVE = {
    13: -0.42, 14: -0.36, 15: -0.31, 16: -0.26, 17: -0.20, 18: -0.15,
    19: -0.09, 20: -0.04, 21: -0.01, 22: 0.01, 23: 0.03, 24: 0.05,
    25: 0.06, 26: 0.06, 27: 0.06, 28: 0.05, 29: 0.03, 30: 0.01,
    31: -0.02, 32: -0.06, 33: -0.10, 34: -0.15, 35: -0.21, 36: -0.27,
    37: -0.34, 38: -0.40, 39: -0.46, 40: -0.52,
}
_AGE_X = np.array(sorted(_AGE_CURVE))
_AGE_Y = np.array([_AGE_CURVE[a] for a in _AGE_X])
_AGE_PEAK = float(_AGE_Y.max())


def age_adjustment(age: float | None) -> float:
    """Peak-Zuschlag: wie viel Rating ein Spieler dieses Alters im Hoch gewinnt."""
    if age is None:
        return 0.0
    a = min(max(age, _AGE_X[0]), _AGE_X[-1])
    return _AGE_PEAK - float(np.interp(a, _AGE_X, _AGE_Y))


# ---------------------------------------------------------------------------
# Daten laden
# ---------------------------------------------------------------------------

def _int(v, default=None):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def load_matches(path: str) -> dict[str, str]:
    """match_id -> competition (fuer die Ausgabe)."""
    comp: dict[str, str] = {}
    try:
        for r in csv.DictReader(open(path, encoding="utf-8")):
            comp[r["match_id"]] = r.get("competition", "")
    except FileNotFoundError:
        pass
    return comp


def load_players(path: str) -> tuple[dict, dict]:
    """Liest players.csv.

    Rueckgabe:
      matches: match_id -> {"home":[appearance...], "away":[...]}
      meta   : pid -> {name, birth_year, teams:set, minutes:int, matches:set}
    Ein `appearance` ist (pid, on, off_eff).
    """
    matches: dict[str, dict[str, list]] = defaultdict(lambda: {"home": [], "away": []})
    meta: dict[str, dict] = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        role = (r.get("role") or "").lower()
        mins = _int(r.get("minutes"), 0) or 0
        starter = role == "starter"
        if not starter and mins <= 0:
            continue  # Bank ohne Einsatz
        name = r.get("name") or ""
        pid = r.get("player_id") or f"name::{name}::{r.get('team','')}"
        on = 0 if starter else _int(r.get("on"), None)
        if on is None:
            continue  # eingesetzt, aber ohne bekannte Einwechselminute -> ueberspringen
        off = _int(r.get("off"), None)
        off_eff = FULLTIME if off is None else max(on, min(off, FULLTIME))
        side = (r.get("side") or "").lower()
        if side not in ("home", "away"):
            continue
        matches[r["match_id"]][side].append((pid, on, off_eff))

        m = meta.setdefault(pid, {"name": name, "birth_year": _int(r.get("birth_year")),
                                  "teams": set(), "minutes": 0, "matches": set()})
        if r.get("team"):
            m["teams"].add(r["team"])
        if m["birth_year"] is None:
            m["birth_year"] = _int(r.get("birth_year"))
        m["minutes"] += mins
        m["matches"].add(r["match_id"])
        if not m["name"]:
            m["name"] = name
    return matches, meta


def load_goals(path: str) -> dict[str, list[tuple[int, str]]]:
    """match_id -> Liste von (minute in [0,89], side)."""
    goals: dict[str, list] = defaultdict(list)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if (r.get("type") or "").lower() != "goal":
            continue
        mn = _int(r.get("minute"), None)
        side = (r.get("team") or "").lower()
        if mn is None or side not in ("home", "away"):
            continue
        goals[r["match_id"]].append((min(max(mn, 0), FULLTIME - 1), side))
    return goals


# ---------------------------------------------------------------------------
# Segmente
# ---------------------------------------------------------------------------

def build_segments(matches: dict, goals: dict) -> list[dict]:
    """Zerlegt jedes Spiel in Segmente mit konstanter Aufstellung."""
    segs: list[dict] = []
    for mid, sides in matches.items():
        home, away = sides["home"], sides["away"]
        if not home or not away:
            continue
        bps = {0, FULLTIME}
        for _, on, off in home + away:
            if 0 < on < FULLTIME:
                bps.add(on)
            if 0 < off < FULLTIME:
                bps.add(off)
        cuts = sorted(bps)
        gl = goals.get(mid, [])
        for t0, t1 in zip(cuts, cuts[1:]):
            if t1 <= t0:
                continue
            hon = [pid for pid, on, off in home if on <= t0 and off >= t1]
            aon = [pid for pid, on, off in away if on <= t0 and off >= t1]
            if not hon or not aon:
                continue
            gh = sum(1 for mn, s in gl if t0 <= mn < t1 and s == "home")
            ga = sum(1 for mn, s in gl if t0 <= mn < t1 and s == "away")
            segs.append({"mid": mid, "dur": t1 - t0, "home": hon, "away": aon,
                         "gh": gh, "ga": ga})
    return segs


# ---------------------------------------------------------------------------
# Design-Matrix + Loesung
# ---------------------------------------------------------------------------

class Model:
    """Baut die (duennbesetzte) Design-Matrix und loest das RAPM-System."""

    def __init__(self, segments: list[dict]):
        pids = sorted({p for s in segments for p in (s["home"] + s["away"])})
        self.pid_idx = {p: i for i, p in enumerate(pids)}
        self.pids = pids
        n = len(pids)
        self.n = n
        self.OFF = 0            # Spalten 0..n-1
        self.DEF = n            # Spalten n..2n-1
        self.C_CONST = 2 * n    # Angriffs-Basiswert
        self.C_HFA = 2 * n + 1  # Heimvorteil
        self.C_MAN = 2 * n + 2  # Ueberzahl-Effekt
        self.ncol = 2 * n + 3

        rows_i, rows_j, rows_v, y, rmatch = [], [], [], [], []
        r = 0
        for s in segments:
            sc = s["dur"] / FULLTIME
            nh, na = len(s["home"]), len(s["away"])
            hi = [self.pid_idx[p] for p in s["home"]]
            ai = [self.pid_idx[p] for p in s["away"]]
            # --- Zeile 1: Heim in der Offensive (y = Heimtore) ---
            for i in hi:
                rows_i.append(r); rows_j.append(self.OFF + i); rows_v.append(sc)
            for i in ai:
                rows_i.append(r); rows_j.append(self.DEF + i); rows_v.append(-sc)
            rows_i += [r, r, r]
            rows_j += [self.C_CONST, self.C_HFA, self.C_MAN]
            rows_v += [sc, sc, (nh - na) * sc]
            y.append(s["gh"]); rmatch.append(s["mid"]); r += 1
            # --- Zeile 2: Gast in der Offensive (y = Gasttore, kein HFA) ---
            for i in ai:
                rows_i.append(r); rows_j.append(self.OFF + i); rows_v.append(sc)
            for i in hi:
                rows_i.append(r); rows_j.append(self.DEF + i); rows_v.append(-sc)
            rows_i += [r, r]
            rows_j += [self.C_CONST, self.C_MAN]
            rows_v += [sc, (na - nh) * sc]
            y.append(s["ga"]); rmatch.append(s["mid"]); r += 1

        self.X = sp.csr_matrix((rows_v, (rows_i, rows_j)), shape=(r, self.ncol))
        self.y = np.asarray(y, dtype=float)
        self.rmatch = np.asarray(rmatch)

    def _reg(self, lam: float) -> sp.csr_matrix:
        """Regularisierungszeilen: sqrt(lam) auf jede Spieler-Spalte (off+def)."""
        k = 2 * self.n
        return sp.csr_matrix((np.full(k, np.sqrt(lam)),
                              (np.arange(k), np.arange(k))), shape=(k, self.ncol))

    def solve(self, lam: float, row_mask: np.ndarray | None = None,
              iter_lim: int = 500) -> np.ndarray:
        X = self.X if row_mask is None else self.X[row_mask]
        y = self.y if row_mask is None else self.y[row_mask]
        A = sp.vstack([X, self._reg(lam)]).tocsr()
        yy = np.concatenate([y, np.zeros(2 * self.n)])
        return lsqr(A, yy, iter_lim=iter_lim, atol=1e-8, btol=1e-8)[0]

    def cv_lambda(self, grid: list[float], seed: int = 0) -> tuple[float, list]:
        """Waehlt Lambda per Match-Holdout (80/20) nach Segment-Tor-MSE."""
        rng = np.random.default_rng(seed)
        uniq = np.array(sorted(set(self.rmatch)))
        test_m = set(rng.choice(uniq, size=max(1, len(uniq) // 5), replace=False))
        test = np.array([m in test_m for m in self.rmatch])
        train = ~test
        report = []
        best, best_mse = grid[0], np.inf
        for lam in grid:
            beta = self.solve(lam, row_mask=train)
            pred = self.X[test] @ beta
            mse = float(np.mean((pred - self.y[test]) ** 2))
            report.append((lam, mse))
            if mse < best_mse:
                best_mse, best = mse, lam
        return best, report


# ---------------------------------------------------------------------------
# Diagnostik: Konnektivitaet
# ---------------------------------------------------------------------------

def connectivity(segments: list[dict], meta: dict, comp_of: dict) -> str:
    """Union-Find ueber Spieler, die im selben Spiel auftraten."""
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    per_match: dict[str, list] = defaultdict(list)
    for s in segments:
        per_match[s["mid"]].extend(s["home"] + s["away"])
    for mid, ps in per_match.items():
        ps = list(set(ps))
        for p in ps[1:]:
            union(ps[0], p)

    comps: dict[str, int] = defaultdict(int)
    for p in parent:
        comps[find(p)] += 1
    sizes = sorted(comps.values(), reverse=True)
    total = sum(sizes)
    multi = sum(1 for p, m in meta.items()
                if len({comp_of.get(x, "") for x in m["matches"]}) > 1)
    lines = [
        f"  Spieler in Ratings      : {total}",
        f"  Komponenten             : {len(sizes)}  (groesste {sizes[0]}"
        f" = {100*sizes[0]/total:.0f}%)",
        f"  kleine Komponenten (<5) : {sum(1 for s in sizes if s < 5)}",
        f"  Spieler in >1 Bewerb    : {multi}  (Bruecken zwischen den Ligen)",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Ausgabe
# ---------------------------------------------------------------------------

def percentile_ranks(values: dict[str, float]) -> dict[str, float]:
    """0 = bester (hoechster Wert), 100 = schlechtester. Fuer eine Kohorte."""
    if not values:
        return {}
    items = sorted(values.items(), key=lambda kv: kv[1], reverse=True)
    n = len(items)
    return {pid: (100.0 * i / (n - 1) if n > 1 else 0.0)
            for i, (pid, _) in enumerate(items)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="OEFB Plus-Minus-Ratings (RAPM).")
    p.add_argument("--players", default="data/players.csv")
    p.add_argument("--events", default="data/events.csv")
    p.add_argument("--matches", default="data/matches.csv")
    p.add_argument("-o", "--out", default="data/ratings.csv")
    p.add_argument("--lam", type=float, default=None,
                   help="Regularisierung. Ohne Angabe wird per CV gewaehlt.")
    p.add_argument("--no-cv", action="store_true", help="Keine CV (nutzt --lam oder 100).")
    p.add_argument("--ref-year", type=int, default=2026,
                   help="Bezugsjahr fuer Alter/Peak (Default: 2026).")
    p.add_argument("--min-minutes", type=int, default=270,
                   help="Mindestminuten fuer die kombinierte Talent-Rangliste.")
    args = p.parse_args(argv)

    comp_of = load_matches(args.matches)
    matches, meta = load_players(args.players)
    goals = load_goals(args.events)
    print(f"Geladen: {len(matches)} Spiele, {len(meta)} Spieler.", file=sys.stderr)

    segments = build_segments(matches, goals)
    tot_goals = sum(s["gh"] + s["ga"] for s in segments)
    print(f"Segmente: {len(segments)} (Ø {sum(s['dur'] for s in segments)/max(1,len(segments)):.1f} min, "
          f"{tot_goals} Tore erfasst).", file=sys.stderr)

    model = Model(segments)
    print(f"Design-Matrix: {model.X.shape[0]} Zeilen × {model.ncol} Spalten "
          f"({model.n} Spieler).", file=sys.stderr)

    if args.no_cv:
        lam = args.lam if args.lam is not None else 100.0
    elif args.lam is not None:
        lam = args.lam
    else:
        grid = [10, 30, 100, 300, 1000, 3000]
        lam, report = model.cv_lambda(grid)
        print("CV (Lambda -> Test-MSE):", file=sys.stderr)
        for l, m in report:
            print(f"    λ={l:<6} MSE={m:.5f}{'   <- best' if l == lam else ''}", file=sys.stderr)
    print(f"Verwende λ = {lam}.", file=sys.stderr)

    beta = model.solve(lam)
    hfa, man = beta[model.C_HFA], beta[model.C_MAN]
    print(f"Heimvorteil={hfa:+.3f} Tore/90, Ueberzahl-Effekt={man:+.3f} Tore/90 pro Mann.",
          file=sys.stderr)

    # Ratings je Spieler zusammenstellen
    ref = args.ref_year
    rows = []
    for pid, i in model.pid_idx.items():
        m = meta.get(pid, {})
        off = float(beta[model.OFF + i])
        deff = float(beta[model.DEF + i])
        total = off + deff
        by = m.get("birth_year")
        age = (ref - by) if by else None
        peak = total + age_adjustment(age)
        comps = sorted({comp_of.get(x, "") for x in m.get("matches", set())} - {""})
        rows.append({
            "player_id": pid, "name": m.get("name", ""),
            "birth_year": by or "", "age": age if age is not None else "",
            "teams": " / ".join(sorted(m.get("teams", []))),
            "competitions": " / ".join(comps),
            "minutes": m.get("minutes", 0), "matches": len(m.get("matches", set())),
            "off": round(off, 4), "def": round(deff, 4),
            "total": round(total, 4), "peak": round(peak, 4),
        })

    # Perzentile je Geburtsjahrgang (0 = bester)
    by_cohort: dict = defaultdict(dict)
    for r in rows:
        if r["birth_year"] != "":
            by_cohort[r["birth_year"]][r["player_id"]] = r["total"]
    pct_total = {}
    for by, vals in by_cohort.items():
        pct_total.update(percentile_ranks(vals))
    pct_peak = {}
    for by in by_cohort:
        vals = {r["player_id"]: r["peak"] for r in rows if r["birth_year"] == by}
        pct_peak.update(percentile_ranks(vals))
    # Kombinierter Rang (Peak + Minuten) je Kohorte – bestes Verfahren im Paper
    comb = {}
    for by in by_cohort:
        cohort = [r for r in rows if r["birth_year"] == by]
        peakr = percentile_ranks({r["player_id"]: r["peak"] for r in cohort})
        minr = percentile_ranks({r["player_id"]: (r["minutes"] if r["minutes"] >= args.min_minutes
                                                  else -1) for r in cohort})
        merged = {pid: (peakr[pid] + minr[pid]) / 2 for pid in peakr}
        comb.update(percentile_ranks({pid: -v for pid, v in merged.items()}))  # kleiner=besser

    for r in rows:
        r["pct_total"] = round(pct_total.get(r["player_id"], ""), 1) if r["player_id"] in pct_total else ""
        r["pct_peak"] = round(pct_peak.get(r["player_id"], ""), 1) if r["player_id"] in pct_peak else ""
        r["pct_talent"] = round(comb.get(r["player_id"], ""), 1) if r["player_id"] in comb else ""

    rows.sort(key=lambda r: r["total"], reverse=True)
    fields = ["player_id", "name", "birth_year", "age", "teams", "competitions",
              "minutes", "matches", "off", "def", "total", "peak",
              "pct_total", "pct_peak", "pct_talent"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"\nRatings -> {args.out} ({len(rows)} Spieler).", file=sys.stderr)

    print("\nKonnektivitaet:", file=sys.stderr)
    print(connectivity(segments, meta, comp_of), file=sys.stderr)

    print("\nTop 10 nach Total-Rating:", file=sys.stderr)
    for r in rows[:10]:
        print(f"  {r['total']:+.3f}  {r['name']:<26} {str(r['birth_year']):<6} "
              f"{r['minutes']:>5}' {r['competitions']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
