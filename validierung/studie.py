#!/usr/bin/env python3
"""Validierungsstudie: (A) erkennt das Rating spaetere Aufsteiger, (B) sagt die Startelf-Staerke Spielausgaenge voraus?

Grundsatz: kein Blick in die Zukunft. Ratings werden nur aus Spielen VOR einem Stichtag gerechnet, geprueft wird danach.

A  Talent-Rueckblick in zwei Zeitfenstern
   F1: lernen 2023/24            -> Ergebnis ab 2025/26 (Profi oder >= 900 Min. Regionalliga)
   F2: lernen 2023/24 + 2024/25  -> Ergebnis ab 2026/27 (Profi oder >= 300 Min. Regionalliga; Saison erst zu einem Drittel gespielt)
B  Spielprognose: Ratings aus Spielen vor 01.07.2025; Startelf-Staerke = Summe der Total-Ratings der elf Starter.
   Kalibrierung der Wahrscheinlichkeiten auf Saison 2025/26, Test auf Saison 2026/27. Vergleich mit Team-Elo
   (reine Mannschaftsstaerke aus Ergebnissen) und der Haeufigkeitsregel. Mass: Ranked Probability Score (kleiner = besser).

Aufruf:  python3 validierung/studie.py [--work <ordner>]   ->  validierung/studie_ergebnis.json
"""
from __future__ import annotations
import argparse, csv, json, math, re, subprocess, sys, tempfile
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm

ROOT = Path(__file__).resolve().parent.parent
YOUTH = re.compile(r"\bU\s?\d|jugend", re.I)


def iso(d):
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", d or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def season_of(i):
    y, mth = int(i[:4]), int(i[5:7]); a = y if mth >= 7 else y - 1
    return f"{a}/{str(a + 1)[2:]}"


def wilson(k, n, z=1.96):
    if n == 0: return (None, None)
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round(100 * (c - h) / d, 1), round(100 * (c + h) / d, 1))


def ratings_until(data, work, cut):
    """Ratings nur aus Spielen vor dem Stichtag (plusminus.py auf gefilterten CSVs)."""
    tag = cut.replace("-", ""); out = work / f"ratings_{tag}.csv"
    if out.exists():
        return {r["player_id"]: r for r in csv.DictReader(open(out, encoding="utf-8"))}
    d = work / tag; d.mkdir(parents=True, exist_ok=True)
    with open(data / "matches.csv", encoding="utf-8") as f:
        rd = csv.DictReader(f); mf = rd.fieldnames; rows = list(rd)
    keep = {r["match_id"] for r in rows if iso(r["date"]) and iso(r["date"]) < cut}
    with open(d / "matches.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=mf); w.writeheader(); w.writerows(r for r in rows if r["match_id"] in keep)
    for name in ("players.csv", "events.csv"):
        with open(data / name, encoding="utf-8") as fi, open(d / name, "w", newline="", encoding="utf-8") as fo:
            rd = csv.reader(fi); w = csv.writer(fo); head = next(rd); w.writerow(head); i = head.index("match_id")
            for r in rd:
                if r[i] in keep: w.writerow(r)
    subprocess.run([sys.executable, str(ROOT / "plusminus.py"), "--players", str(d / "players.csv"), "--events", str(d / "events.csv"),
                    "--matches", str(d / "matches.csv"), "-o", str(out), "--ref-year", cut[:4], "--lam", "30"],
                   check=True, cwd=ROOT, stderr=subprocess.DEVNULL)
    return {r["player_id"]: r for r in csv.DictReader(open(out, encoding="utf-8"))}


def num(v):
    try: return float(v)
    except (TypeError, ValueError): return None


def rps(p, y):
    """Ranked Probability Score fuer 3 geordnete Ausgaenge; p = (Heim, Remis, Gast), y = 0/1/2."""
    c1 = p[:, 0] - (y == 0); c2 = p[:, 0] + p[:, 1] - (y <= 1)
    return float(np.mean((c1 ** 2 + c2 ** 2) / 2))


def fit_probit(X, y):
    """Geordnetes Probit: P(Heim) = 1 - Phi(c2 - xb), P(Gast) = Phi(c1 - xb). Rueckgabe: predict(Xneu)."""
    k = X.shape[1]
    def nll(t):
        b, c1, c2 = t[:k], t[k], t[k] + math.exp(t[k + 1]); z = X @ b
        pa = norm.cdf(c1 - z); ph = 1 - norm.cdf(c2 - z); pd = 1 - pa - ph
        p = np.where(y == 0, ph, np.where(y == 1, pd, pa))
        return -np.sum(np.log(np.clip(p, 1e-12, 1)))
    r = minimize(nll, np.r_[np.zeros(k), -0.3, math.log(0.6)], method="BFGS")
    t = r.x
    def predict(Xn):
        z = Xn @ t[:k]; c1, c2 = t[k], t[k] + math.exp(t[k + 1])
        pa = norm.cdf(c1 - z); ph = 1 - norm.cdf(c2 - z)
        return np.c_[ph, 1 - pa - ph, pa]
    return predict, t


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--data", default=str(ROOT / "data")); ap.add_argument("--work", default=None)
    a = ap.parse_args(); data = Path(a.data); work = Path(a.work or tempfile.mkdtemp(prefix="studie_")); work.mkdir(parents=True, exist_ok=True)

    # ---------------- Daten laden ----------------
    M = {}
    for r in csv.DictReader(open(data / "matches.csv", encoding="utf-8")):
        i = iso(r["date"])
        if not i or not r["home_team"] or r["score_home"] in ("", None): continue
        M[r["match_id"]] = {"iso": i, "comp": r["competition"], "home": r["home_team"], "away": r["away_team"],
                            "sh": int(float(r["score_home"])), "sa": int(float(r["score_away"])), "youth": bool(YOUTH.search(r["competition"]))}
    APP = defaultdict(list); name = {}
    for r in csv.DictReader(open(data / "players.csv", encoding="utf-8")):
        if r["match_id"] in M:
            APP[r["match_id"]].append((r["side"], r["role"], r["player_id"], int(float(r["minutes"] or 0))))
            if r["player_id"]: name[r["player_id"]] = r["name"]
    prof = json.load(open(data / "players_profiles.json", encoding="utf-8"))
    def pro(pid):
        b = (prof.get(pid) or {}).get("bewerbe_aktuell") or ""
        return 1 if "ADMIRAL Bundesliga" in b else (2 if "ADMIRAL 2. Liga" in b else 0)
    res = {"daten": {"spiele": len(M), "von": min(m["iso"] for m in M.values()), "bis": max(m["iso"] for m in M.values()),
                     "bewerbe": len({m["comp"] for m in M.values()}), "spieler": len(name)}}

    # ---------------- A  Talent-Rueckblick ----------------
    def backtest(cut, last_from, out_from, rl_need, years, label):
        R = ratings_until(data, work, cut)
        ymin = defaultdict(int); rl = defaultdict(int)
        for mid, m in M.items():
            for side, role, pid, mins in APP[mid]:
                if not pid: continue
                if last_from <= m["iso"] < cut and m["youth"]: ymin[pid] += mins
                elif m["iso"] >= out_from and not m["youth"] and "Regionalliga" in m["comp"]: rl[pid] += mins
        S = []
        for pid, mn in ymin.items():
            r = R.get(pid)
            if not r or mn < 900: continue
            by, pt, pk = num(r["birth_year"]), num(r["pct_talent"]), num(r["peak"])
            if by is None or pt is None or pk is None or not (years[0] <= by <= years[1]): continue
            p = pro(pid)
            S.append({"by": int(by), "min": mn, "pt": pt, "peak": pk, "profi": bool(p), "hit": bool(p or rl[pid] >= rl_need)})
        n = len(S); hits = sum(x["hit"] for x in S); base = hits / n
        def bands(order):
            L = sorted(S, key=order); out = []
            for lab, lo, hi in (("Top 2 %", 0, .02), ("Top 5 %", 0, .05), ("Top 10 %", 0, .10), ("Top 20 %", 0, .20),
                                ("20 bis 50 %", .20, .50), ("untere Hälfte", .50, 1.0)):
                g = L[int(round(lo * n)):max(int(round(hi * n)), int(round(lo * n)) + 1)]; h = sum(x["hit"] for x in g); pr = sum(x["profi"] for x in g)
                lo_, hi_ = wilson(h, len(g))
                out.append({"band": lab, "n": len(g), "treffer": h, "quote": round(100 * h / len(g), 1), "ci": [lo_, hi_],
                            "profi": pr, "lift": round((h / len(g)) / base, 2), "erfasst": round(100 * h / hits, 1)})
            return out
        topn = []
        L = sorted(S, key=lambda x: (x["pt"], -x["peak"]))
        for k in (10, 20, 30, 50):
            topn.append({"n": k, "treffer": sum(x["hit"] for x in L[:k]), "profi": sum(x["profi"] for x in L[:k])})
        return {"label": label, "cut": cut, "out_from": out_from, "rl_need": rl_need, "jahrgaenge": list(years), "n": n, "treffer": hits,
                "profi": sum(x["profi"] for x in S), "basisquote": round(100 * base, 1),
                "nach_talent": bands(lambda x: (x["pt"], -x["peak"])),            # Rating + Minuten (Talent-Rang)
                "nach_minuten": bands(lambda x: -x["min"]),                       # Vergleich: nur Einsatzminuten
                "topn": topn}
    res["talent"] = [backtest("2024-07-01", "2023-07-01", "2025-07-01", 900, (2005, 2008), "Fenster 1"),
                     backtest("2025-07-01", "2024-07-01", "2026-07-01", 300, (2006, 2009), "Fenster 2")]

    # ---------------- B  Spielprognose ----------------
    CUT = "2025-07-01"; R = ratings_until(data, work, CUT)
    tot = {pid: num(r["total"]) for pid, r in R.items() if num(r["total"]) is not None}
    # Team-Elo ueber alle Spiele chronologisch (Wert VOR dem Spiel wird verwendet)
    elo = defaultdict(lambda: 1500.0); K, HFA = 24.0, 60.0; elo_pre = {}; frozen = None; elo_fr = {}
    for mid, m in sorted(M.items(), key=lambda kv: (kv[1]["iso"], kv[0])):
        if frozen is None and m["iso"] >= CUT: frozen = dict(elo)          # Elo-Stand am Stichtag (gleicher Wissensstand wie die Ratings)
        if frozen is not None: elo_fr[mid] = frozen.get(m["home"], 1500.0) - frozen.get(m["away"], 1500.0)
        eh, ea = elo[m["home"]], elo[m["away"]]; elo_pre[mid] = eh - ea
        exp = 1 / (1 + 10 ** (-(eh + HFA - ea) / 400)); sc = 1.0 if m["sh"] > m["sa"] else (0.5 if m["sh"] == m["sa"] else 0.0)
        elo[m["home"]] = eh + K * (sc - exp); elo[m["away"]] = ea - K * (sc - exp)
    T = []
    for mid, m in M.items():
        if m["iso"] < CUT: continue
        st = {"home": [], "away": []}
        for side, role, pid, mins in APP[mid]:
            if role == "starter" and side in st: st[side].append(pid)
        if len(st["home"]) < 9 or len(st["away"]) < 9: continue
        sh = sum(tot.get(p, 0.0) for p in st["home"]); sa = sum(tot.get(p, 0.0) for p in st["away"])
        known = sum(1 for p in st["home"] + st["away"] if p in tot) / (len(st["home"]) + len(st["away"]))
        T.append({"mid": mid, "season": season_of(m["iso"]), "youth": m["youth"], "x": sh - sa, "sh": sh, "sa": sa, "e": elo_pre[mid] / 400.0, "ef": elo_fr.get(mid, 0.0) / 400.0,
                  "gd": m["sh"] - m["sa"], "y": 0 if m["sh"] > m["sa"] else (1 if m["sh"] == m["sa"] else 2), "known": known,
                  "home": m["home"], "away": m["away"]})
    arr = lambda k, L: np.array([t[k] for t in L], float)
    tr = [t for t in T if t["season"] == "2025/26"]; te = [t for t in T if t["season"] == "2026/27"]
    ytr, yte = arr("y", tr).astype(int), arr("y", te).astype(int)
    freq = np.bincount(ytr, minlength=3) / len(ytr)
    models = {"Häufigkeitsregel": lambda L: np.tile(freq, (len(L), 1))}
    for lab, cols in (("Mannschaftsstärke laufend (Team-Elo)", ["e"]), ("Mannschaftsstärke, Stand Stichtag", ["ef"]),
                      ("Startelf-Stärke (Spieler-Ratings), Stand Stichtag", ["x"]), ("Startelf-Stärke + Mannschaftsstärke laufend", ["x", "e"])):
        Xtr = np.c_[[arr(c, tr) for c in cols]].T; pred, _ = fit_probit(Xtr, ytr)
        models[lab] = (lambda L, cols=cols, pred=pred: pred(np.c_[[arr(c, L) for c in cols]].T))
    def score(L, y):
        o = {}
        for lab, f in models.items():
            p = f(L); o[lab] = {"rps": round(rps(p, y), 4), "logloss": round(float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1)))), 4),
                                "treffer": round(100 * float(np.mean(np.argmax(p, 1) == y)), 1)}
        return o
    B = {"cut": CUT, "n_kalibrierung": len(tr), "n_test": len(te), "haeufigkeit_train": [round(100 * float(x), 1) for x in freq],
         "bekannt": round(100 * float(np.mean(arr("known", T))), 1), "bekannt_test": round(100 * float(np.mean(arr("known", te))), 1),
         "test_gesamt": score(te, yte),
         "test_erwachsene": score([t for t in te if not t["youth"]], np.array([t["y"] for t in te if not t["youth"]])),
         "test_jugend": score([t for t in te if t["youth"]], np.array([t["y"] for t in te if t["youth"]])),
         "test_startelf_bekannt": score([t for t in te if t["known"] >= .85], np.array([t["y"] for t in te if t["known"] >= .85])),
         "n_startelf_bekannt": sum(1 for t in te if t["known"] >= .85),
         "n_test_erw": sum(1 for t in te if not t["youth"]), "n_test_jug": sum(1 for t in te if t["youth"])}
    # Kalibrierung in Toren: Steigung der Regression Tordifferenz ~ Startelf-Differenz (Modell erwartet 1)
    x, gd = arr("x", T), arr("gd", T); A = np.c_[np.ones(len(x)), x]; coef, *_ = np.linalg.lstsq(A, gd, rcond=None)
    resid = gd - A @ coef; se = math.sqrt(float(resid @ resid) / (len(x) - 2) / float(((x - x.mean()) ** 2).sum()))
    B["tore"] = {"n": len(T), "achsenabschnitt": round(float(coef[0]), 3), "steigung": round(float(coef[1]), 3), "se": round(se, 3),
                 "r": round(float(np.corrcoef(x, gd)[0, 1]), 3), "r_elo": round(float(np.corrcoef(arr("e", T), gd)[0, 1]), 3)}
    # Fuenftel nach Startelf-Differenz
    q = np.quantile(x, [0, .2, .4, .6, .8, 1.0]); Q = []
    for i in range(5):
        g = [t for t in T if (q[i] <= t["x"] <= q[i + 1] if i == 4 else q[i] <= t["x"] < q[i + 1])]; yy = np.array([t["y"] for t in g])
        Q.append({"von": round(float(q[i]), 2), "bis": round(float(q[i + 1]), 2), "n": len(g), "heim": round(100 * float(np.mean(yy == 0)), 1),
                  "remis": round(100 * float(np.mean(yy == 1)), 1), "gast": round(100 * float(np.mean(yy == 2)), 1),
                  "ppg": round(float(np.mean(np.where(yy == 0, 3, np.where(yy == 1, 1, 0)))), 2), "gd": round(float(np.mean([t["gd"] for t in g])), 2)})
    B["fuenftel"] = Q
    # Mannschaftsebene Saison 2026/27: mittlere Startelf-Staerke vs. Punkte je Spiel
    tm = defaultdict(lambda: [0.0, 0, 0]); 
    for t in te:
        ph = 3 if t["y"] == 0 else (1 if t["y"] == 1 else 0); pa = 3 if t["y"] == 2 else (1 if t["y"] == 1 else 0)
        for k, s, p in ((t["home"], t["sh"], ph), (t["away"], t["sa"], pa)):
            tm[(k, t["youth"])][0] += s; tm[(k, t["youth"])][1] += p; tm[(k, t["youth"])][2] += 1
    teams = [{"s": v[0] / v[2], "ppg": v[1] / v[2], "n": v[2], "youth": k[1]} for k, v in tm.items() if v[2] >= 8]
    B["teams"] = {"n": len(teams), "r": round(float(np.corrcoef([t["s"] for t in teams], [t["ppg"] for t in teams])[0, 1]), 3),
                  "punkte": [[round(t["s"], 3), round(t["ppg"], 3), int(t["youth"])] for t in teams]}
    # Wert eines Spielers in Punkten: +0,10 Rating in der Startelf, ausgeglichenes Spiel (nur Erwachsene, alle Testspiele)
    Ad = [t for t in T if not t["youth"]]; pred, tpar = fit_probit(np.c_[arr("x", Ad)], np.array([t["y"] for t in Ad]))
    def pts(xv):
        p = pred(np.array([[xv]]))[0]; return 3 * p[0] + p[1], p
    # neutraler Platz: Mittel aus Heim- und Gastsicht
    def neutral(d):
        a, pa_ = pts(d); b, pb_ = pts(-d); return (a + (3 * pb_[2] + pb_[1])) / 2, (pa_[0] + pb_[2]) / 2
    p0, w0 = neutral(0.0); out = []
    for d in (0.05, 0.10, 0.20, 0.30):
        p1, w1 = neutral(d); out.append({"delta": d, "siegchance_pp": round(100 * (w1 - w0), 1), "punkte_je_spiel": round(p1 - p0, 3), "punkte_30": round(30 * (p1 - p0), 1)})
    B["spielerwert"] = {"n": len(Ad), "basis_sieg": round(100 * w0, 1), "basis_punkte": round(p0, 2), "stufen": out}
    res["prognose"] = B
    (ROOT / "validierung" / "studie_ergebnis.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------------- Textausgabe ----------------
    for t in res["talent"]:
        print(f"\n{t['label']}: lernen bis {t['cut']}, Ergebnis ab {t['out_from']}; n={t['n']}, Treffer {t['treffer']} (Basis {t['basisquote']} %), Profi {t['profi']}")
        for lab in ("nach_talent", "nach_minuten"):
            print("  " + lab)
            for b in t[lab]: print(f"     {b['band']:<14} n={b['n']:>4} Treffer {b['treffer']:>3} Quote {b['quote']:>5} % CI {b['ci']} Lift {b['lift']} erfasst {b['erfasst']} % Profi {b['profi']}")
        print("  Top-N:", t["topn"])
    print("\nPROGNOSE", {k: B[k] for k in ("n_kalibrierung", "n_test", "haeufigkeit_train", "bekannt", "tore")})
    for k in ("test_gesamt", "test_erwachsene", "test_jugend", "test_startelf_bekannt"):
        print(" ", k); [print(f"     {m:<36} {v}") for m, v in B[k].items()]
    for qq in Q: print("  ", qq)
    print("  Teams:", B["teams"]["n"], "r =", B["teams"]["r"]); print("  Spielerwert:", B["spielerwert"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
