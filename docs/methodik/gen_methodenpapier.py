# -*- coding: utf-8 -*-
"""gen_methodenpapier.py — Methodenpapier „Mannschaftsstärke, Ergebniswahrscheinlichkeiten und Trainerwirkung“
im Strykerlabs-Hauslayout (Skill strykerlabs-paper).

Alle Zahlen und Grafiken werden aus den Ausgabedateien der ÖFB-Pipeline gelesen:
  data/oefb.sqlite (build_db.py), data/matches.csv (Trainer je Spiel), data/ratings.csv und
  data/ratings_meta.json (plusminus.py). Ein neuer Lauf der Pipeline und dieses Skripts ergibt
  eine Fassung mit den dann gültigen Werten.

Aufruf:  python3 docs/methodik/gen_methodenpapier.py
Ausgabe: docs/methodik/Mannschaftsstaerke_Methodenpapier_Fassung<N>_<Datum>.html/.pdf
"""
import csv, json, math, re, sqlite3, sys, datetime as dt
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path.home()/".claude/skills/strykerlabs-paper/scripts"))
from paper import Paper
from figstyle import plt, svg, GREEN, CA, CB, CC, GRAU, HELLGRAU, INK, MUTE, SEQ
from matplotlib.patches import FancyBboxPatch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT/"data"
FASSUNG = "2"
HEUTE = dt.date.today()
STAND = f"{HEUTE.day}. {['Januar','Februar','März','April','Mai','Juni','Juli','August','September','Oktober','November','Dezember'][HEUTE.month-1]} {HEUTE.year}"
TRAINER_MD = Path.home()/"projekte/kontexttransfer/kontexttransfer_modell/07_trainer_performance/Trainer_Performance_Methodik_DE.md"

# ============================================================ Formatierung
def de(x, d=0, sign=False):
    if x is None or (isinstance(x, float) and math.isnan(x)): return "—"
    s = f"{float(x):{'+' if sign else ''},.{d}f}".replace(",", "§").replace(".", ",").replace("§", ".")
    return s.replace("-", "−")
def pz(x, d=1): return de(100*x, d) + " %"
def jug(comp): return bool(re.search(r"\bU\s?\d|jugend", comp or "", re.I))

SHORT = {"1. HYPO TIROL Landesliga Ost": "LL Tirol Ost", "HYPO TIROL Liga": "Tirol Liga", "11teamsports 1. Landesliga": "1. LL NÖ",
         "Burgenland Energie Landesliga": "LL Bgld", "Burgenlandliga": "Bgld Liga", "LT1 OÖ Liga": "OÖ Liga",
         "VOL.AT-Eliteliga": "Eliteliga Vbg", "VN.at-Eliteliga": "Eliteliga Vbg (VN)", "Wiener Stadtliga": "Wr. Stadtliga",
         "Regionalliga Süd Kärnten": "RL Süd Ktn", "Regionalliga Süd Stmk": "RL Süd Stmk", "Kärntner Liga": "Ktn Liga",
         "Salzburger Liga": "Sbg Liga", "Landesliga": "LL Stmk", "Oberliga Mitte West": "OL Mitte West",
         "Oberliga Nord": "OL Nord", "Oberliga Süd Ost": "OL Süd Ost"}
def short(c):
    if c in SHORT: return SHORT[c]
    return (c.replace("ÖFB Jugendregionalliga Ost", "JRL Ost").replace("ÖFB Jugendregionalliga", "JRL")
             .replace("ÖFB Jugendliga", "JL").replace("Regionalliga", "RL"))

def rps(p, o):
    """Ranked Probability Score für (H, D, A)."""
    return 0.5*((p[0]-o[0])**2 + (p[0]+p[1]-o[0]-o[1])**2)

# ============================================================ Daten
con = sqlite3.connect(DATA/"oefb.sqlite")
META = json.load(open(DATA/"ratings_meta.json", encoding="utf-8"))
M = [dict(zip(("mid", "comp", "season", "iso", "home", "away", "sh", "sa"), r)) for r in con.execute(
    "SELECT match_id, competition, season, iso_date, home_team, away_team, score_home, score_away FROM matches")]
MR = [m for m in M if m["sh"] is not None and m["sa"] is not None]
N_M, N_MR = len(M), len(MR)
SEASONS = sorted({m["season"] for m in M if m["season"]})
CUR = SEASONS[-1]
COMPS = sorted({m["comp"] for m in M if m["comp"]})

def hda(rows):
    n = len(rows); h = sum(m["sh"] > m["sa"] for m in rows); d = sum(m["sh"] == m["sa"] for m in rows)
    return n, h/n, d/n, 1-(h+d)/n, sum(m["sh"]+m["sa"] for m in rows)/n
CAT = {"Erwachsene": [m for m in MR if not jug(m["comp"])], "Jugend": [m for m in MR if jug(m["comp"])]}
HDA = {k: hda(v) for k, v in CAT.items()}; HDA["gesamt"] = hda(MR)
BASE = HDA["gesamt"][1:4]

def outcome(m): return (1, 0, 0) if m["sh"] > m["sa"] else (0, 1, 0) if m["sh"] == m["sa"] else (0, 0, 1)
RPS = {"Gleichverteilung": np.mean([rps((1/3, 1/3, 1/3), outcome(m)) for m in MR]),
       "Häufigkeit gesamt": np.mean([rps(BASE, outcome(m)) for m in MR]),
       "Häufigkeit je Kategorie": np.mean([rps(HDA["Jugend" if jug(m["comp"]) else "Erwachsene"][1:4], outcome(m)) for m in MR])}
bycomp = defaultdict(list)
for m in MR: bycomp[m["comp"]].append(m)
HDA_C = {c: hda(v) for c, v in bycomp.items() if c}
def _wil(k, n, z=1.96):
    p = k/n; d = 1+z*z/n; c = (p+z*z/(2*n))/d; h = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return c-h, c+h
HEIM_OUT = [c for c, v in HDA_C.items() if v[0] >= 60 and not (_wil(round(v[1]*v[0]), v[0])[0] <= BASE[0] <= _wil(round(v[1]*v[0]), v[0])[1])]
RPS["Häufigkeit je Bewerb*"] = np.mean([rps(HDA_C[m["comp"]][1:4], outcome(m)) for m in MR if m["comp"]])
RPS_TRAINER_QUOTE = None
if TRAINER_MD.exists():
    t = TRAINER_MD.read_text(encoding="utf-8"); mm = re.search(r"RPS Quote (\d),(\d+)", t)
    if mm: RPS_TRAINER_QUOTE = float(f"{mm.group(1)}.{mm.group(2)}")

# Mannschaften, Ligagruppen
teams = defaultdict(set); tgames = Counter()
for m in M:
    for t in (m["home"], m["away"]):
        tgames[t] += 1
        if m["comp"]: teams[t].add(m["comp"])
def components(edges, nodes):
    par = {n: n for n in nodes}
    def f(x):
        while par[x] != x: par[x] = par[par[x]]; x = par[x]
        return x
    for a, b in edges: par[f(a)] = f(b)
    g = defaultdict(list)
    for n in nodes: g[f(n)].append(n)
    return sorted(g.values(), key=len, reverse=True)
team_edges = Counter()
for cs in teams.values():
    cs = sorted(cs)
    for i in range(len(cs)):
        for j in range(i+1, len(cs)): team_edges[(cs[i], cs[j])] += 1
pcomp = defaultdict(set)
for pid, comp in con.execute("SELECT a.player_id, m.competition FROM appearances a JOIN matches m USING(match_id) "
                             "WHERE a.minutes > 0 AND a.player_id IS NOT NULL AND m.competition != ''"):
    pcomp[pid].add(comp)
player_edges = Counter()
for cs in pcomp.values():
    cs = sorted(cs)
    for i in range(len(cs)):
        for j in range(i+1, len(cs)): player_edges[(cs[i], cs[j])] += 1
GRP_T = components(team_edges, COMPS); GRP_P = components(player_edges, COMPS)
N_TEAMS = len(tgames); N_TEAMS20 = sum(v >= 20 for v in tgames.values())
N_PLAYERS_MULTI = sum(len(v) > 1 for v in pcomp.values())
def grp_name(g):
    s = " ".join(g)
    if "U15" in s: return "U15"
    if "U16" in s: return "U16"
    if "U18" in s: return "U18"
    if "Regionalliga Ost" in g: return "Ost"
    return "West, Mitte, Süd"

# Ratings
R = list(csv.DictReader(open(DATA/"ratings.csv", encoding="utf-8")))
RAT = {r["player_id"]: float(r["total"]) for r in R}
TT = np.array([[float(r["total"]), float(r["total_cur"])] for r in R if int(r["minutes"]) >= META["min_minutes"]])

# Startelf-Kaderstärke (in der Stichprobe, aktuelle Ratings)
lineup = defaultdict(lambda: [0.0, 0.0, 0, 0])
for mid, side, pid in con.execute("SELECT match_id, side, player_id FROM appearances WHERE role='starter' AND player_id IS NOT NULL"):
    if pid in RAT:
        k = 0 if side == "home" else 1; lineup[mid][k] += RAT[pid]; lineup[mid][2+k] += 1
LU = [(lineup[m["mid"]][0]-lineup[m["mid"]][1], outcome(m)) for m in MR
      if m["mid"] in lineup and lineup[m["mid"]][2] >= 9 and lineup[m["mid"]][3] >= 9]
LU.sort(key=lambda x: x[0])
DEC = np.array_split(np.array([[d, *o] for d, o in LU]), 10)

# Tore nach Spielstand (aus Sicht der torschießenden Mannschaft)
ev = defaultdict(list); bad = set()
for mid, minute, team in con.execute("SELECT match_id, minute, team FROM events WHERE type='goal'"):
    if minute is None or team not in ("home", "away"): bad.add(mid); continue
    ev[mid].append((minute, team))
STATE = Counter(); n_goal_used = 0
for mid, gl in ev.items():
    if mid in bad: continue
    h = a = 0
    for minute, team in sorted(gl):
        d = (h-a) if team == "home" else (a-h)
        STATE[max(-2, min(3, d))] += 1; n_goal_used += 1
        if team == "home": h += 1
        else: a += 1
N_GOALS_EV = sum(len(v) for v in ev.values())

# Poisson-Raten (Erwachsene) und Hebel eines Tores
ER = CAT["Erwachsene"]
LAM_H = np.mean([m["sh"] for m in ER]); LAM_A = np.mean([m["sa"] for m in ER])
def pois(l, k): return math.exp(-l)*l**k/math.factorial(k)
def ep_home(t, d):
    rest = max(0, 90-t)/90; lh, la = LAM_H*rest, LAM_A*rest
    ph = [pois(lh, k) for k in range(12)]; pa = [pois(la, k) for k in range(12)]
    w = dr = 0.0
    for i, x in enumerate(ph):
        for j, y in enumerate(pa):
            if d+i-j > 0: w += x*y
            elif d+i-j == 0: dr += x*y
    return 3*w + dr
def hebel(t, d): return ep_home(t, d+1) - ep_home(t, d-1)

# Trainer-Amtszeiten
MC = [r for r in csv.DictReader(open(DATA/"matches.csv", encoding="utf-8")) if (r.get("ok") or "").lower() == "true"]
N_COACH_H = sum(bool(r["coach_home"].strip()) for r in MC); N_COACH_A = sum(bool(r["coach_away"].strip()) for r in MC)
cg = defaultdict(list)
for r in MC:
    mm = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", r["date"] or "")
    if not mm: continue
    d = dt.date(int(mm[3]), int(mm[2]), int(mm[1])); j = jug(r["competition"])
    for t, c in ((r["home_team"], r["coach_home"]), (r["away_team"], r["coach_away"])):
        if c.strip(): cg[(t, j)].append((d, c.strip()))
COACHES = {c for v in cg.values() for _, c in v}
def spells(seq):
    sp = []
    for c in seq:
        if not sp or sp[-1][0] != c: sp.append([c, 0])
        sp[-1][1] += 1
    return sp
RAW, CLEAN = {False: [], True: []}, {False: [], True: []}
N_SUB = {False: 0, True: 0}; CLUBS = defaultdict(set)
for (t, j), x in cg.items():
    x.sort(); sp = spells([c for _, c in x]); RAW[j] += [s[1] for s in sp]
    i = 0; out = []
    while i < len(sp):
        if out and i+1 < len(sp) and sp[i][1] <= 2 and sp[i+1][0] == out[-1][0]:
            out[-1][1] += sp[i][1] + sp[i+1][1]; N_SUB[j] += 1; i += 2; continue
        out.append(list(sp[i])); i += 1
    CLEAN[j] += [s[1] for s in out]
    for c, n in out:
        if n >= 10: CLUBS[c].add(t)
N_MULTI_CLUB = sum(len(v) >= 2 for v in CLUBS.values())
N20 = {j: sum(n >= 20 for n in CLEAN[j]) for j in (False, True)}
N1 = {j: sum(n == 1 for n in RAW[j]) for j in (False, True)}
MED20 = float(np.median([n for j in (False, True) for n in CLEAN[j] if n >= 20]))

# Streuung der Punkte um die Grunderwartung (für die Power-Rechnung)
res = []
for m in MR:
    b = HDA["Jugend" if jug(m["comp"]) else "Erwachsene"]
    xh, xa = 3*b[1]+b[2], 3*b[3]+b[2]; o = outcome(m)
    res += [3*o[0]+o[1]-xh, 3*o[2]+o[1]-xa]
SIGMA = float(np.std(res))
def n_power(delta): return (2.8*SIGMA/delta)**2

# ============================================================ Grafiken
def box(ax, x, y, w, h, t, sub="", fc=HELLGRAU, tc=INK, ec="none", fs=8.4):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=1.0", fc=fc, ec=ec, lw=1.3))
    ax.text(x+w/2, y+h*(0.64 if sub else 0.5), t, ha="center", va="center", color=tc, fontsize=fs, fontweight="bold")
    if sub: ax.text(x+w/2, y+h*0.28, sub, ha="center", va="center", color=tc, fontsize=6.4, linespacing=1.2)
def arrow(ax, a, b, c="#888", lw=1.0, ls="-"):
    ax.annotate("", b, a, arrowprops=dict(arrowstyle="-|>", color=c, lw=lw, ls=ls, mutation_scale=9, shrinkA=0, shrinkB=0))

def fig_aufbau():
    fig, ax = plt.subplots(figsize=(8.2, 3.5)); ax.set_axis_off(); ax.set_xlim(0, 100); ax.set_ylim(0, 44)
    for x, t in [(1, "Daten"), (27, "Methode (Bausteine)"), (58, "Ergebnis"), (82, "Anwendung")]:
        ax.text(x, 42.5, t, fontsize=8, color=MUTE)
    box(ax, 1, 27, 20, 11, "Ergebnisse", "Endstand, Datum, Bewerb")
    box(ax, 1, 14, 20, 11, "Aufstellungen", "Segmente, Tor-Minuten")
    box(ax, 1, 1, 20, 11, "Trainer je Spiel", "aus den Spielberichten")
    rows = [("M1 Team-Elo", 33), ("M2 Wahrscheinlichkeiten", 25), ("M3 Kaderstärke", 17), ("M4 Punkte-Plus-Minus", 9), ("M5 Trainermodul", 1)]
    for t, y in rows: box(ax, 27, y, 25, 6.5, t, fc=CA, tc="white", fs=7.6)
    box(ax, 58, 27, 20, 11, "Stärke und P(Sieg)", "je Mannschaft und Spiel", fc=GREEN, tc="white")
    box(ax, 58, 14, 20, 11, "Rating in Punkten", "je Spieler, pro 90 Min.", fc=GREEN, tc="white")
    box(ax, 58, 1, 20, 11, "Trainerkennzahlen", "je Amtszeit, geprüft", fc=GREEN, tc="white")
    box(ax, 82, 27, 17, 11, "Klub", "Prognose, Simulation", fc="white", ec=GREEN)
    box(ax, 82, 14, 17, 11, "Scouting", "Ratings, Ligaabstand", fc="white", ec=GREEN)
    box(ax, 82, 1, 17, 11, "Trainerwahl", "Profil je Amtszeit", fc="white", ec=GREEN)
    for y in (32.5, 19.5, 6.5): arrow(ax, (21.4, y), (26.6, y if y != 32.5 else 36)); arrow(ax, (78.4, y), (81.6, y))
    for y0, y1 in [(36, 32.5), (28, 32.5), (20, 32.5), (12, 19.5), (4, 6.5)]: arrow(ax, (52.4, y0+0.3), (57.6, y1))
    return svg(fig)

def fig_saisons():
    fig, ax = plt.subplots(figsize=(7.4, 2.7))
    e = [sum(1 for m in M if m["season"] == s and not jug(m["comp"])) for s in SEASONS]
    j = [sum(1 for m in M if m["season"] == s and jug(m["comp"])) for s in SEASONS]
    ax.bar(SEASONS, e, color=CA, width=.6); ax.bar(SEASONS, j, bottom=e, color=CC, width=.6)
    for i, s in enumerate(SEASONS):
        ax.text(i, e[i]+j[i]+60, de(e[i]+j[i]), ha="center", fontsize=8)
    ax.text(len(SEASONS)-1, e[-1]/2, "Erwachsene", ha="center", va="center", color="white", fontsize=7.5)
    ax.text(len(SEASONS)-1, e[-1]+j[-1]/2, "Jugend", ha="center", va="center", color="white", fontsize=7.5)
    ax.set_ylabel("Spiele"); ax.set_ylim(0, max(a+b for a, b in zip(e, j))*1.15)
    ax.text(len(SEASONS)-1, -0.13*ax.get_ylim()[1], "laufend", ha="center", fontsize=7, color=MUTE, transform=ax.transData)
    return svg(fig)

def fig_hda():
    fig, ax = plt.subplots(figsize=(7.4, 1.9))
    labs = ["Erwachsene", "Jugend", "gesamt"]
    for i, k in enumerate(labs):
        n, h, d, a, g = HDA[k]; left = 0
        for v, c, t in [(h, CA, "Heimsieg"), (d, GRAU, "Remis"), (a, CB, "Auswärtssieg")]:
            ax.barh(i, v, left=left, color=c, height=.62)
            ax.text(left+v/2, i, f"{t} {pz(v)}" if i == 0 else pz(v), ha="center", va="center", color="white", fontsize=7.3)
            left += v
        ax.text(1.01, i, f"n = {de(n)}\n{de(g, 2)} Tore/Spiel", va="center", fontsize=7, color=MUTE)
    ax.set_yticks(range(3)); ax.set_yticklabels(labs); ax.set_xlim(0, 1); ax.invert_yaxis()
    ax.set_xticks([0, .25, .5, .75, 1]); ax.set_xticklabels(["0 %", "25 %", "50 %", "75 %", "100 %"]); ax.grid(False)
    return svg(fig)

def fig_netz():
    order = [c for g in GRP_T for c in sorted(g)]
    n = len(order); gap = 0.5
    ang, a = {}, 0.0
    step = (2*math.pi - gap*len(GRP_T)) / n
    for g in GRP_T:
        for c in sorted(g): ang[c] = a; a += step
        a += gap
    pos = {c: (math.cos(v), math.sin(v)) for c, v in ang.items()}
    gcol = {}
    pal = [CA, CB, CC, "#8a6d3b", "#6a4c93"]
    for i, g in enumerate(GRP_T):
        for c in g: gcol[c] = pal[i % len(pal)]
    fig, axs = plt.subplots(1, 2, figsize=(8.4, 4.8))
    for ax, E, titel, col in [(axs[0], team_edges, f"über Mannschaften: {len(GRP_T)} Gruppen", None),
                              (axs[1], player_edges, f"über Spieler: {len(GRP_P)} Gruppe", GREEN)]:
        ax.set_axis_off(); ax.set_aspect("equal"); ax.set_xlim(-1.95, 1.95); ax.set_ylim(-1.9, 1.8)
        mx = max(E.values())
        for (u, v), w in E.items():
            if u not in pos or v not in pos: continue
            (x1, y1), (x2, y2) = pos[u], pos[v]
            ax.plot([x1, x2], [y1, y2], color=col or gcol[u], lw=0.4+2.2*math.log1p(w)/math.log1p(mx), alpha=.55, zorder=1)
        for c, (x, y) in pos.items():
            ax.scatter([x], [y], s=28, color=gcol[c], zorder=3, edgecolor="white", lw=.6)
            deg = math.degrees(math.atan2(y, x)); right = -90 <= deg <= 90
            ax.text(1.08*x, 1.08*y, short(c), fontsize=5.4, ha="left" if right else "right", va="center",
                    rotation=deg if right else deg-180, rotation_mode="anchor", color=INK)
        ax.set_title(titel, fontsize=8.5, loc="center")
    for i, g in enumerate(GRP_T):
        axs[0].text(-1.9, -1.45-0.11*i, f"{grp_name(g)} ({len(g)})", color=pal[i % len(pal)], fontsize=6.5)
    axs[1].text(-1.9, -1.75, f"{de(len(player_edges))} verbundene Bewerbspaare;\nLinienstärke wächst mit der Zahl\nder Spieler mit Einsätzen in beiden",
                fontsize=6.5, color=MUTE)
    return svg(fig)

def fig_hexbin():
    fig, ax = plt.subplots(figsize=(7.4, 3.4))
    hb = ax.hexbin(TT[:, 0], TT[:, 1], gridsize=55, cmap=plt.matplotlib.colors.LinearSegmentedColormap.from_list("g", ["#ffffff"] + SEQ), mincnt=1, bins="log")
    lo, hi = TT.min(), TT.max(); ax.plot([lo, hi], [lo, hi], ls="--", color=GRAU, lw=1)
    ax.set_xlabel("Total-Rating, alle Saisonen gleich gewichtet (Tore/90)"); ax.set_ylabel("Total akt., zeitgewichtet (Tore/90)")
    ax.text(.02, .95, f"r = {de(META['corr_total_cur_minmin'], 2)}\nn = {de(len(TT))} Spieler ≥ {META['min_minutes']} Min.",
            transform=ax.transAxes, va="top", fontsize=8)
    cb = fig.colorbar(hb, ax=ax, pad=.01); cb.set_label("Spieler je Feld (log)", fontsize=7.5); cb.ax.tick_params(labelsize=7)
    return svg(fig)

def fig_widerspruch():
    fig, ax = plt.subplots(figsize=(8.2, 3.3)); ax.set_axis_off(); ax.set_xlim(0, 100); ax.set_ylim(0, 40)
    box(ax, 1, 26, 22, 11, "Spieler i", "β_i aus Plus-Minus", fc=CA, tc="white")
    box(ax, 32, 26, 24, 11, "Kaderstärke S_T", "Summe der Startelf", fc=CA, tc="white")
    box(ax, 66, 26, 30, 11, "Mannschaftsstärke R_T", "Team-Elo aus Ergebnissen", fc=GREEN, tc="white")
    box(ax, 66, 4, 30, 11, "Mannschaftsmehrwert u_T", "R_T − (a + b·S_T): System, Trainer", fc="white", ec=GREEN)
    arrow(ax, (23.4, 31.5), (31.6, 31.5)); arrow(ax, (56.4, 31.5), (65.6, 31.5))
    ax.text(61, 33.6, "b·S_T", ha="center", fontsize=7.5, color=MUTE)
    arrow(ax, (81, 25.6), (81, 15.4), c=GREEN)
    ax.annotate("", (12, 25.6), (66, 20), arrowprops=dict(arrowstyle="-|>", color=CB, lw=1.2, ls="--", connectionstyle="arc3,rad=-0.25", mutation_scale=9))
    ax.text(30, 13.5, "falsch: R_T als Regressor zurück in die Spieler-Regression\nergibt doppelte Zählung, Kollinearität, Zirkularität",
            fontsize=7.3, color=CB, ha="center")
    ax.text(8, 3, "richtig: getrennt schätzen, danach vergleichen\n(Weg C) oder Zielgröße wechseln (Wege A und B)", fontsize=7.3, color=CC)
    return svg(fig)

def wilson(k, n, z=1.96):
    p = k/n; d = 1+z*z/n; c = (p+z*z/(2*n))/d; h = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return c-h, c+h
def fig_heim():
    rows = sorted([(c, *HDA_C[c]) for c in HDA_C if HDA_C[c][0] >= 60], key=lambda r: r[2])
    fig, ax = plt.subplots(figsize=(7.4, 5.4))
    for i, (c, n, h, d, a, g) in enumerate(rows):
        lo, hi = wilson(round(h*n), n)
        col = CC if jug(c) else CA
        ax.plot([lo, hi], [i, i], color=col, lw=1.4); ax.scatter([h], [i], color=col, s=18, zorder=3)
        ax.text(hi+.005, i, f"n = {de(n)}", va="center", fontsize=6.2, color=MUTE)
    ax.axvline(BASE[0], color=GREEN, ls="--", lw=1)
    ax.text(BASE[0]+.07, -.45, f"gestrichelt: alle Spiele {pz(BASE[0])}", color=GREEN, fontsize=7.5)
    ax.set_yticks(range(len(rows))); ax.set_yticklabels([short(r[0]) for r in rows], fontsize=7)
    ax.set_xlabel("Anteil Heimsiege mit 95-%-Intervall"); ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{de(100*v)} %"))
    ax.set_title("blau: Erwachsene · dunkelgrün: Jugend", fontsize=7.5, color=MUTE, loc="right")
    ax.set_ylim(-.7, len(rows)+.3)
    return svg(fig)

TH2 = math.log(0.6/0.4)                                  # Remisband bei gleichen Stärken = beobachtete Remisquote
ALPHA = math.log(10)/400                                 # Steigung wie im klassischen Elo (Annahme)
def F(z): return 1/(1+math.exp(-z))
H_ELO = (TH2 - math.log((1-BASE[0])/BASE[0]))/ALPHA      # Heimvorteil so, dass P(Heimsieg) = beobachtete Quote
def fig_ologit():
    x = np.linspace(-400, 400, 241)
    ph = np.array([1-F(TH2-ALPHA*(v+H_ELO)) for v in x]); pa = np.array([F(-TH2-ALPHA*(v+H_ELO)) for v in x]); pd_ = 1-ph-pa
    fig, ax = plt.subplots(figsize=(7.4, 3.0))
    ax.stackplot(x, pa, pd_, ph, colors=[CB, GRAU, CA], alpha=.9)
    ax.text(-330, .2, "Auswärtssieg", color="white", fontsize=8); ax.text(-40, .5, "Remis", color="white", fontsize=8)
    ax.text(230, .8, "Heimsieg", color="white", fontsize=8)
    ax.axvline(0, color="white", lw=1, ls="--")
    i0 = 120
    ax.text(8, 1.02, f"gleich stark: {pz(ph[i0])} / {pz(pd_[i0])} / {pz(pa[i0])}", fontsize=7.3, color=INK)
    ax.set_xlim(-400, 400); ax.set_ylim(0, 1); ax.set_xlabel("Elo-Differenz Heim − Gast vor dem Spiel (ohne Heimvorteil)")
    ax.set_ylabel("Wahrscheinlichkeit"); ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{de(100*v)} %")); ax.grid(False)
    return svg(fig)

def fig_lineup():
    fig, ax = plt.subplots(figsize=(7.4, 3.0))
    xs = np.arange(10); H_ = [d[:, 1].mean() for d in DEC]; D_ = [d[:, 2].mean() for d in DEC]; A_ = [d[:, 3].mean() for d in DEC]
    ax.bar(xs, A_, color=CB, width=.72); ax.bar(xs, D_, bottom=A_, color=GRAU, width=.72)
    ax.bar(xs, H_, bottom=np.array(A_)+np.array(D_), color=CA, width=.72)
    for i in (0, 9):
        ax.text(i, A_[i]+D_[i]+H_[i]/2, pz(H_[i], 0), ha="center", va="center", color="white", fontsize=7.5)
        ax.text(i, A_[i]/2, pz(A_[i], 0), ha="center", va="center", color="white", fontsize=7.5)
    ax.set_xticks(xs); ax.set_xticklabels([f"{i+1}" for i in xs])
    ax.set_xlabel("Zehntel der Differenz der Startelf-Ratings (1 = Gast klar stärker, 10 = Heim klar stärker)")
    ax.set_ylabel("Anteil"); ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{de(100*v)} %")); ax.set_ylim(0, 1); ax.grid(False)
    ax.set_xlim(-.6, 11.2)
    for yy, t, c in [(.85, "Heimsieg", CA), (.5, "Remis", GRAU), (.15, "Auswärtssieg", CB)]: ax.text(9.55, yy, t, fontsize=7, color=c, va="center")
    return svg(fig)

def fig_hebel():
    t = np.arange(0, 90, 1)
    fig, ax = plt.subplots(figsize=(7.4, 3.0))
    ends = []
    for d, c in [(0, GREEN), (-1, CB), (1, CA), (2, GRAU), (3, HELLGRAU)]:
        y = [hebel(v, d) for v in t]; ax.plot(t, y, color=c, lw=2 if d == 0 else 1.4)
        lab = {0: "Gleichstand", -1: "1 Tor hinten", 1: "1 Tor vorne", 2: "2 Tore vorne", 3: "3 Tore vorne"}[d]
        ends.append([y[-1], lab, c if d != 3 else MUTE])
    ends.sort(key=lambda e: e[0])
    for i in range(1, len(ends)): ends[i][0] = max(ends[i][0], ends[i-1][0] + 0.16)
    for yy, lab, c in ends: ax.text(89.5, yy, " " + lab, va="center", fontsize=7, color=c)
    ax.set_xlim(0, 104); ax.set_xticks([0, 15, 30, 45, 60, 75, 90])
    ax.set_xlabel("Spielminute, Sicht der Heimmannschaft"); ax.set_ylabel("Hebel eines Tores (erwartete Punkte)")
    return svg(fig)

def fig_spielstand():
    keys = [-2, -1, 0, 1, 2, 3]; labs = ["≤ 2 hinten", "1 hinten", "gleich", "1 vorne", "2 vorne", "≥ 3 vorne"]
    v = np.array([STATE[k] for k in keys]); s = v/v.sum()
    fig, ax = plt.subplots(figsize=(7.4, 2.6))
    cols = [GRAU, CB, GREEN, CA, GRAU, HELLGRAU]
    ax.bar(labs, s, color=cols, width=.62)
    for i, x in enumerate(s): ax.text(i, x+.006, pz(x), ha="center", fontsize=7.8)
    ax.set_ylabel("Anteil der Tore"); ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{de(100*v)} %"))
    ax.set_xlabel("Spielstand vor dem Tor, aus Sicht der torschießenden Mannschaft")
    ax.text(.99, .92, f"n = {de(n_goal_used)} Tore mit Minute", transform=ax.transAxes, ha="right", fontsize=7.5, color=MUTE)
    return svg(fig)

def fig_amtszeiten():
    fig, axs = plt.subplots(1, 2, figsize=(8.0, 2.8), sharey=True)
    bins = [1, 2, 3, 5, 10, 20, 30, 50, 80, 200]
    for ax, j, t in [(axs[0], False, "Erwachsene"), (axs[1], True, "Jugend")]:
        hr, _ = np.histogram(RAW[j], bins=bins); hc, _ = np.histogram(CLEAN[j], bins=bins)
        x = np.arange(len(hr))
        ax.bar(x-.2, hr, width=.4, color=GRAU); ax.bar(x+.2, hc, width=.4, color=GREEN)
        ax.set_xticks(x); ax.set_xticklabels(["1", "2", "3–4", "5–9", "10–19", "20–29", "30–49", "50–79", "80+"], fontsize=6.8)
        ax.axvline(4.5, color=CC, ls="--", lw=1); ax.set_title(f"{t}: {N20[j]} Amtszeiten ≥ 20 Spiele", fontsize=8.2)
        ax.set_xlabel("Spiele je Folge desselben Trainers")
    axs[0].set_ylabel("Anzahl"); axs[1].text(.98, .9, "grau: roh\ngrün: Vertretungen bereinigt", transform=axs[1].transAxes, ha="right", fontsize=7.5, va="top")
    return svg(fig)

def fig_power():
    d = np.linspace(0.08, 0.5, 100)
    fig, ax = plt.subplots(figsize=(7.4, 2.8))
    ax.plot(d, [n_power(v) for v in d], color=GREEN, lw=2)
    for v in (0.1, 0.2, 0.3):
        nn = n_power(v); ax.scatter([v], [nn], color=GREEN, s=16, zorder=3)
        ax.text(v+.008, nn*1.08, f"{de(v, 1)} Punkte/Spiel: {de(nn)} Spiele", fontsize=7.3)
    ax.axhline(MED20, color=GRAU, ls="--", lw=1); ax.text(.49, MED20*1.1, f"Median der Amtszeiten ≥ 20 Spiele: {de(MED20)} Spiele", ha="right", fontsize=7, color=MUTE)
    ax.set_yscale("log"); ax.set_xlabel("wahrer Trainereffekt (Punkte je Spiel über Erwartung)")
    ax.set_ylabel("nötige Spiele (80 % Power, α = 5 %)")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: de(v)))
    return svg(fig)

NUTZEN = [  # 2 = Hauptnutzen, 1 = Nebennutzen
    ("Scouting", [1, 0, 2, 2, 0]), ("Sportdirektion", [2, 2, 2, 1, 1]), ("Trainerbewertung", [1, 2, 1, 0, 2]),
    ("Verband, Nachwuchs", [2, 1, 1, 0, 1]), ("Produkt, MCP", [2, 2, 1, 1, 1])]
def fig_matrix():
    fig, ax = plt.subplots(figsize=(7.4, 2.7))
    cols = ["M1 Team-Elo", "M2 Wahrsch.", "M3 Kaderstärke", "M4 Punkte-PM", "M5 Trainer"]
    for i, (z, v) in enumerate(NUTZEN):
        for j, w in enumerate(v):
            ax.add_patch(plt.Rectangle((j, i), .94, .86, color=[HELLGRAU, "#bfe6d8", GREEN][w]))
            ax.text(j+.47, i+.43, ["–", "Neben", "Haupt"][w], ha="center", va="center", fontsize=7.5, color="white" if w == 2 else INK)
    ax.set_xlim(0, 5); ax.set_ylim(len(NUTZEN), 0); ax.set_xticks(np.arange(5)+.47); ax.set_xticklabels(cols, fontsize=7.6)
    ax.set_yticks(np.arange(len(NUTZEN))+.43); ax.set_yticklabels([z for z, _ in NUTZEN]); ax.grid(False)
    for s in ax.spines.values(): s.set_visible(False)
    ax.tick_params(length=0); ax.xaxis.tick_top()
    return svg(fig)

def fig_baseline():
    items = list(RPS.items())
    if RPS_TRAINER_QUOTE: items.append(("Wettquote Bundesliga (Ref.)", RPS_TRAINER_QUOTE))
    fig, ax = plt.subplots(figsize=(7.4, 2.6))
    y = np.arange(len(items))
    cols = [GRAU]*len(RPS) + ([CC] if RPS_TRAINER_QUOTE else [])
    cols[1] = GREEN
    ax.barh(y, [v for _, v in items], color=cols, height=.6)
    for i, (_, v) in enumerate(items): ax.text(v+.001, i, de(v, 3), va="center", fontsize=7.8)
    ax.set_yticks(y); ax.set_yticklabels([k for k, _ in items]); ax.invert_yaxis()
    ax.set_xlim(.18, .26); ax.set_xlabel("Ranked Probability Score (kleiner ist besser)")
    return svg(fig)

PHASEN = [("P0 Datenaufbereitung", 2.5), ("P1 Team-Elo, Wahrscheinlichkeiten", 3.5), ("Entscheidung 1", 0), ("P2 Ligaverknüpfung", 2.5),
          ("P3 Kaderstärke, Kombination", 3.5), ("Entscheidung 2", 0), ("P4 Punkte-Plus-Minus", 3), ("P5 Trainermodul", 4.5),
          ("P6 Integration Dashboard, MCP", 3.5), ("P7 Validierungsbericht", 2)]
def fig_gantt():
    fig, ax = plt.subplots(figsize=(7.4, 3.2)); t = 0
    for i, (n, d) in enumerate(PHASEN):
        if d == 0:
            ax.scatter([t], [i], marker="D", color=CB, s=36, zorder=3); ax.text(t+.4, i, n, va="center", fontsize=7.5, color=CB)
        else:
            ax.barh(i, d, left=t, color=GREEN if n.startswith(("P1", "P3", "P4", "P5")) else CA, height=.55)
            ax.text(t+d+.3, i, n, va="center", fontsize=7.5); t += d
    ax.set_yticks([]); ax.invert_yaxis(); ax.set_xlim(0, t+12); ax.set_xlabel("Arbeitstage (Mitte der Schätzung, kumuliert)")
    ax.set_title("grün: Modellbausteine · blau: Daten und Integration · Raute: Entscheidung", fontsize=7.3, color=MUTE, loc="left")
    return svg(fig)

# ============================================================ Paper
P = Paper(titel="Mannschaftsstärke, Ergebniswahrscheinlichkeiten und Trainerwirkung aus ÖFB-Ergebnisdaten",
          untertitel="Erweiterung des Plus-Minus-Modells um Team-Elo, Punkte-Plus-Minus und ein Trainermodul",
          dokumenttyp="Methodenpapier", fassung=FASSUNG, stand=STAND, modul="oefb", status="intern · Konzept, nicht umgesetzt")

E, J = HDA["Erwachsene"], HDA["Jugend"]
P.zusammenfassung(
    f"<p>Das ÖFB-Unterhaus-Modell bewertet {de(len(R))} Spieler aus {len(COMPS)} Bewerben mit einem Plus-Minus-Rating in Toren pro "
    f"90 Minuten. Es sagt nicht, wie stark eine Mannschaft ist, mit welcher Wahrscheinlichkeit sie gewinnt, wer Spiele entscheidet "
    f"und was der Trainer beiträgt. Dieses Papier beschreibt fünf Bausteine, die allein aus Ergebnissen, Aufstellungen und Trainern "
    f"der {de(N_M)} Spiele rechnen: Team-Elo, Ergebniswahrscheinlichkeiten, Kaderstärke der Startelf, ein Rating in Punkten statt "
    f"Toren und ein Trainermodul. Der scheinbare Widerspruch, dass Plus-Minus die Mannschaftsstärke herausrechnet und Elo sie misst, "
    f"löst sich, wenn Elo Maßstab statt Erklärgröße ist. Zwei Befunde prägen die Methodik: Über Mannschaften zerfallen die Bewerbe in "
    f"{len(GRP_T)} getrennte Gruppen, über Spieler bilden sie {len(GRP_P)}; und nach Bereinigung von {de(N_SUB[False]+N_SUB[True])} "
    f"Vertretungen bleiben {de(N20[False])} Amtszeiten Erwachsener und {de(N20[True])} der Jugend mit mindestens 20 Spielen. "
    f"Die Messlatte jeder Prognose ist der Ranked Probability Score der Häufigkeitsregel, {de(RPS['Häufigkeit gesamt'], 3)}. "
    f"Umgesetzt ist noch nichts; Abschnitt 14 enthält einen Plan in acht Phasen mit zwei Entscheidungspunkten.</p>")

P.abschnitt("problem", "Problemstellung und Zielsetzung", f"""<style>.kern{{break-inside:avoid}}</style>
<p>Ein Sportdirektor in der Regionalliga, ein Scout auf der Suche nach Spielern aus Landesligen und eine Akademie, die einen Trainer
sucht, stellen dieselben vier Fragen: <em>Wie stark ist diese Mannschaft wirklich? Mit welcher Wahrscheinlichkeit gewinnt sie das
nächste Spiel? Welche Spieler entscheiden Spiele? Was hat der Trainer daran?</em> Im Unterhaus gibt es dafür weder Wettquoten noch
xG noch Marktwerte. Es gibt nur Ergebnisse, Aufstellungen mit Wechselminuten, Tore mit Minute und den Trainer im Spielbericht.</p>
<p><strong>Ziel</strong> ist eine Methodik, die diese vier Fragen allein aus den vorhandenen Daten beantwortet, an das bestehende
Plus-Minus-Rating anschließt und jede Aussage gegen eine einfache Regel prüft.</p>
{P.tabelle("Forschungsfragen.", ["Nr.", "Frage"], [
 ["F1", "Wie gut lassen sich Ausgänge von Amateur- und Jugendspielen allein aus vergangenen Ergebnissen vorhersagen?"],
 ["F2", "Verbessert die Kaderstärke der tatsächlichen Startelf die Prognose über ein Team-Elo hinaus?"],
 ["F3", "Welche Spieler erhöhen die Gewinnwahrscheinlichkeit, und wie weicht diese Rangliste von der Torrangliste ab?"],
 ["F4", "Gibt es einen über Amtszeiten und Klubs stabilen Trainereffekt auf Punkte, Mannschaftsmehrwert und Spielerentwicklung?"]])}
<p><strong>Abgrenzung.</strong> Nicht Teil dieses Papiers: Wettquoten als Eingangsgröße, xG und Eventdaten über Tore und Karten
hinaus, Bundesliga und 2. Liga sowie eine eigene Schätzung der Alterskurve. Umgesetzt ist noch keiner der Bausteine.</p>
{P.figur("Aufbau: Aus drei Datenbeständen rechnen fünf Bausteine drei Ergebnisse, die Klub, Scouting und Trainerwahl nutzen. "
         "Die Bausteine bauen aufeinander auf; M1 und M2 sind Voraussetzung für M3 und M5.", fig_aufbau())}
""")

P.einordnung(
    anknuepfung={"daten": "oefb.at-Spielberichte als eigene Quelle; Quoten nur zur Stichprobenprüfung",
                 "trainer": "Logik, Kennzahlen und Pflichtprüfungen des Trainermoduls werden übernommen; Erwartung aus Ergebnismodell statt Quote",
                 "ligamodell": "Punkte je 90 Minuten sind über den Wert eines Ligapunkts in Geld übersetzbar",
                 "impact": "Punkte-Plus-Minus liefert Spielerwert in Punkten für Ligen ohne Eventdaten",
                 "scouting": "Ratings, Ligaabstände und Mannschaftskontext für Data Checks aus dem Unterhaus",
                 "strategie": "Saisonsimulation und Trainerprofile für Klubs unterhalb der Bundesliga"},
    konzepte=["Gewinnwahrscheinlichkeit aus Quoten", "Wert eines Ligapunkts", "Spielerwert in Ligapunkten",
              "Plus-Minus-Rating (RAPM)", "Team-Elo und Ergebniswahrscheinlichkeit", "Punkte-Plus-Minus", "Mannschaftsmehrwert"],
    text_davor="<p>Das ÖFB-Unterhaus-Modell ist die einzige Messung unterhalb der Bundesliga. Dieses Papier ergänzt den bisher offenen "
               "Kontextring „Mannschaft“ und überträgt das Trainer-Performance-Modell in Ligen ohne Wettmarkt.</p>")

n_seg = META["segments"]
P.abschnitt("daten", "Datenbasis", f"""
{P.tabelle("Bestände (Stand der Datenbank, " + str(META['built'])[:10] + ").", ["Bestand", "Umfang", "Quelle", "Verwendung"], [
 ["Spiele", f"{de(N_M)}, davon {de(N_MR)} mit Endstand", "oefb.at, Spielbericht", "M1, M2, Validierung"],
 ["Saisonen", f"{SEASONS[0]} bis {CUR} (laufend)", "oefb.at", "Zeitgewichtung, Saisonübergang"],
 ["Bewerbe", f"{len(COMPS)}: Regional-, Landes-, Oberligen, ÖFB-Jugendligen U15–U18", "oefb.at", "Ligaverknüpfung"],
 ["Mannschaften", f"{de(N_TEAMS)}, davon {de(N_TEAMS20)} mit ≥ 20 Spielen", "Spielbericht", "M1, M5"],
 ["Spieler mit Rating", f"{de(len(R))}, davon {de(N_PLAYERS_MULTI)} in mehr als einem Bewerb", "plusminus.py", "M3, Ligabrücke"],
 ["Segmente", f"{de(n_seg)}, Ø {de(META['segment_minutes_mean'], 1)} Min., {de(META['goals_in_segments'])} Tore", "plusminus.py", "M4"],
 ["Tore mit Minute", f"{de(n_goal_used)} von {de(N_GOALS_EV)} Tor-Ereignissen", "Spielbericht, fix_events.py", "M4"],
 ["Trainer je Spiel", f"Heim {de(N_COACH_H)}, Gast {de(N_COACH_A)} von {de(len(MC))}", "Spielbericht", "M5"]], "llll", breit=True)}
{P.figur(f"Spiele je Saison nach Kategorie. Der Bestand wächst mit jeder Saison, weil Bewerbe hinzukommen; {CUR} läuft noch.", fig_saisons())}
<p>Jedes Prognosemodell muss die Grundverteilung der Ausgänge treffen. Jugendspiele enden seltener remis
({pz(J[2])} gegen {pz(E[2])}) und torreicher ({de(J[4], 2)} gegen {de(E[4], 2)} Tore). Die Schwellen der Modelle werden deshalb je
Kategorie geschätzt.</p>
{P.figur("Ausgänge je Kategorie. Der Heimvorteil ist in beiden Kategorien deutlich; die Remisquote der Jugend liegt vier "
         "Prozentpunkte tiefer.", fig_hda())}
<h3>Struktur: Ligen hängen über Spieler zusammen, nicht über Mannschaften</h3>
<p>Verbindet man zwei Bewerbe, sobald eine Mannschaft in beiden gespielt hat, entstehen {len(GRP_T)} getrennte Gruppen:
{", ".join(f"{grp_name(g)} ({len(g)})" for g in GRP_T)}. Verbindet man sie über Spieler mit Einsätzen in beiden, sind
{de(len(player_edges))} Bewerbspaare verbunden und es bleibt {len(GRP_P)} Gruppe. Ein reines Ergebnis-Elo kann deshalb eine
Ost- nicht mit einer West-Mannschaft vergleichen und eine U18 nicht mit einer Landesliga. Das Plus-Minus-Modell kann es.</p>
{P.figur("Verbindungen zwischen den Bewerben. Links über Mannschaften (Auf- und Abstieg): fünf Inseln. Rechts über Spieler: ein "
         "zusammenhängendes Netz. Die Spieler-Ratings sind deshalb die Brücke für Vergleiche zwischen Ligen und Jahrgängen.", fig_netz())}
{P.kernaussage("Kernaussagen", [f"{de(N_MR)} Spiele mit Endstand, {len(COMPS)} Bewerbe, {len(SEASONS)} Saisonen.",
   f"Über Mannschaften {len(GRP_T)} Ligagruppen, über Spieler {len(GRP_P)}: Ligavergleiche brauchen die Spielerbrücke.",
   f"Trainer stehen in {pz(min(N_COACH_H, N_COACH_A)/len(MC))} der Spielberichte."])}
""")

P.abschnitt("bestand", "Ausgangspunkt: das Plus-Minus-Rating", f"""
<p>Die Methodik folgt Hvattum (2020) und Hvattum, Kriegl und Čulík (2023). Jedes Spiel wird an jeder Ein- und Auswechslung und jeder
Roten Karte in Segmente konstanter Aufstellung geschnitten. Jedes Segment liefert zwei Beobachtungen, eine je Mannschaft im Angriff
(Ilardi 2007). Für die Heimtore in einem Segment der Dauer <var>d</var> gilt näherungsweise:</p>
<div class="formula">g<sub>H</sub> ≈ (d/90) · ( c + h + Σ<sub>i∈Heim</sub> β<sub>i</sub><sup>O</sup> − Σ<sub>j∈Gast</sub> β<sub>j</sub><sup>D</sup> + μ·(n<sub>H</sub> − n<sub>A</sub>) )</div>
<p>β<sup>O</sup>, β<sup>D</sup> sind Offensiv- und Defensivrating je Spieler in Toren pro 90 Minuten, <var>c</var> die Grundtorrate,
<var>h</var> der Heimvorteil, μ der Effekt eines Mannes mehr. Geschätzt wird mit gewichteten Kleinsten Quadraten und Ridge-Strafterm:</p>
<div class="formula">β̂ = argmin<sub>β</sub> Σ<sub>r</sub> w<sub>r</sub>·(y<sub>r</sub> − x<sub>r</sub>β)² + λ·Σ<sub>k</sub> β<sub>k</sub>²</div>
{P.tabelle("Kennzahlen des aktuellen Laufs (data/ratings_meta.json).", ["Größe", "alle Saisonen gleich", "zeitgewichtet"], [
 ["λ (Kreuzvalidierung)", de(META["lambda"]), de(META["lambda_cur"])],
 ["Heimvorteil (Tore/90)", de(META["home_advantage"], 3, True), de(META["home_advantage_cur"], 3, True)],
 ["Überzahl je Spieler (Tore/90)", de(META["man_advantage"], 3, True), de(META["man_advantage_cur"], 3, True)],
 ["Halbwertszeit", "—", f"{de(META['half_life_days'])} Tage, Bezug {META['ref_date_cur']}"]], "lnn")}
{P.figur(f"Total-Rating und zeitgewichtete Variante „Total akt.“ je Spieler. Beide stimmen weitgehend überein (r = "
         f"{de(META['corr_total_cur_minmin'], 2)}); die zeitgewichtete Variante ist enger um null, weil alte Saisonen weniger zählen "
         "und die Regularisierung relativ stärker wirkt.", fig_hexbin())}
<p><strong>Grenzen des Bestands.</strong> (1) Kein Mannschaftsmaß und keine Wahrscheinlichkeit je Spiel. (2) Jedes Tor zählt gleich:
das 1:0 in der 85. Minute so viel wie das 6:0. (3) Trainer sind unsichtbar, ihr Beitrag landet bei den Spielern. (4) Die
Kreuzvalidierung bewertet Tore je Segment, nicht Ausgänge von Spielen; ob die Ratings Ergebnisse vorhersagen, ist ungeprüft.</p>
{P.kernaussage("Kernaussagen", ["Das Rating misst Spieler, nicht Mannschaften.", "Ob es Ergebnisse vorhersagt, ist bisher nicht geprüft; M3 holt das nach."])}
""")

P.abschnitt("widerspruch", "Der Widerspruch und seine Auflösung", f"""
<p>Plus-Minus beantwortet: <em>Wie viel trägt Spieler i bei, gegeben mit wem und gegen wen er spielt?</em> Es gibt der Mannschaft
absichtlich keinen eigenen Term. Elo beantwortet: <em>Wie stark ist die Mannschaft als Ganzes?</em> Diese Stärke entsteht zum großen
Teil aus denselben Spielern. Formal mit Kaderstärke S<sub>T</sub> = Σ<sub>i∈Elf</sub>(β<sub>i</sub><sup>O</sup> + β<sub>i</sub><sup>D</sup>):</p>
<div class="formula">R<sub>T</sub> ≈ a + b·S<sub>T</sub> + u<sub>T</sub></div>
<p>u<sub>T</sub> ist, was die Mannschaft über die Summe ihrer Spieler hinaus leistet: Abstimmung, System, Trainer, Zusammenhalt.
Elo als Erklärgröße in die Spieler-Regression aufzunehmen ist aus drei Gründen falsch:</p>
<ol class="korr">
<li><strong>Doppelte Zählung.</strong> Elo erklärt einen Teil dessen, was die Spieler geleistet haben, und das Modell zieht ihn ab.
Gerade die Spieler, die eine Mannschaft stark machen, verlieren am meisten.</li>
<li><strong>Kollinearität.</strong> Elo ist innerhalb einer Saison fast konstant und damit nahezu eine Linearkombination der Stammspieler.</li>
<li><strong>Zirkularität.</strong> Elo verarbeitet dieselben Tore, die die Zielgröße bilden; jede Kreuzvalidierung wird verzerrt.</li>
</ol>
{P.figur("Getrennt schätzen, danach vergleichen. Die Kaderstärke speist die Mannschaftsstärke; der Rest u<sub>T</sub> ist der "
         "Mannschaftsmehrwert. Der gestrichelte Rückweg in die Spieler-Regression ist der Fehler, den die Erweiterung vermeidet.", fig_widerspruch())}
<p><strong>Auflösung.</strong> Der Gedanke, über die Mannschaftsstärke zu erkennen, wer Gewinnwahrscheinlichkeiten erhöht, bleibt
richtig, gehört aber an drei andere Stellen. <em>Weg A</em> wechselt die Zielgröße: Veränderung der erwarteten Punkte statt Tore
(M4, nach Kharrat, McHale und López Peña 2020). <em>Weg B</em> behält Tore und gewichtet Segmente nach dem Hebel eines Tores im
jeweiligen Spielstand. <em>Weg C</em> liest die Differenz u<sub>T</sub> als Mannschafts- und Trainereffekt (M3, M5).</p>
<p><strong>Offener Rest.</strong> Auch Weg A braucht für die erwarteten Punkte eine Stärkeannahme. Mit Elo kehrte der Widerspruch
teilweise zurück. Die Hauptvariante rechnet deshalb ohne Stärke, nur aus Minute, Spielstand, Heimrecht und Spielerzahl; Elo dient nur
der Sensitivitätsprüfung. Und u<sub>T</sub> ist nur identifiziert, wo Spieler oder Trainer wechseln: {de(N_PLAYERS_MULTI)} Spieler
in mehreren Bewerben und {de(N_MULTI_CLUB)} Trainer mit mindestens zwei Klubs tragen diese Identifikation.</p>
{P.kernaussage("Kernaussagen", ["Elo ist Maßstab, nicht Erklärgröße.", "Drei Wege: Zielgröße Punkte, Hebelgewichte, Differenz u<sub>T</sub>."])}
""")

P.abschnitt("m1", "Baustein M1: Team-Elo", f"""
<p><strong>Idee.</strong> Nach jedem Spiel wandert Stärke vom Verlierer zum Sieger, umso mehr, je überraschender das Ergebnis und
je größer die Tordifferenz war (Hvattum und Arntzen 2010; Pi-Rating als Vergleich nach Constantinou und Fenton 2013).</p>
<div class="formula">E<sub>H</sub> = 1 / (1 + 10<sup>−(R<sub>H</sub> + H<sub>L</sub> − R<sub>A</sub>)/400</sup>),
&nbsp; R<sub>H</sub> ← R<sub>H</sub> + K·(1 + |ΔTore|)<sup>γ</sup>·(S<sub>H</sub> − E<sub>H</sub>)</div>
<p><strong>Schritte.</strong> (1) K, γ und der Heimvorteil H<sub>L</sub> werden durch Minimierung des RPS auf einer rollierenden
Stichprobe gewählt, nie gesetzt. (2) Zum Saisonbeginn Rückzug zum Bewerbsmittel, R ← μ<sub>L</sub> + ρ·(R − μ<sub>L</sub>); in der
Jugend getrennt und stärker, weil im Folgejahr ein anderer Jahrgang spielt. (3) Aufsteiger übernehmen ihre Stärke aus der Unterliga,
sonst Bewerbsmittel minus Aufsteigerabschlag. (4) Ligaverknüpfung über einen Niveauabstand δ<sub>L</sub> je Bewerb, geschätzt über
die Spielerbrücke aus Abbildung 5: Plus-Minus mit regularisiertem Term je Bewerb und Saison; R<sub>global</sub> = R + δ<sub>L</sub>.</p>
<p>Der Heimvorteil ist nicht überall gleich. Die Heimsiegquoten der Bewerbe streuen sichtbar um das Gesamtmittel; ob die Unterschiede
über den Zufall hinausgehen, prüft M1 mit H<sub>L</sub> je Bewerb gegen ein gemeinsames H.</p>
{P.figur("Heimsiegquote je Bewerb mit 95-%-Intervall (Bewerbe mit mindestens 60 Spielen). Die gestrichelte Linie ist das Mittel aller "
         f"Spiele. {len(HEIM_OUT)} Bewerbe ({', '.join(short(c) for c in sorted(HEIM_OUT))}) schließen das Gesamtmittel mit ihrem Intervall aus; "
         "bei so vielen Bewerben kann das auch Zufall sein. Ein Heimvorteil je Bewerb ist deshalb zu prüfen, nicht zu setzen.", fig_heim())}
<p><strong>Grenzen.</strong> Elo reagiert verzögert und ist ohne Schritt 4 nur innerhalb einer Ligagruppe vergleichbar.</p>
{P.kernaussage("Kernaussagen", ["Parameter aus der rollierenden Prognosegüte, nicht gesetzt.", "Jugend: starker Rückzug zum Mittel je Saison.",
                                "Vergleiche über Ligagruppen nur mit δ<sub>L</sub>."])}
""")

P.abschnitt("m2", "Baustein M2: Ergebniswahrscheinlichkeiten", f"""
<p><strong>Idee.</strong> Die Elo-Differenz wird über ein geordnetes Logit in Wahrscheinlichkeiten für Heimsieg, Remis und
Auswärtssieg übersetzt (Hvattum und Arntzen 2010). Vergleichsmodelle: Remis nach Davidson (1970) und ein Poisson-Tormodell mit
Zeitgewichtung (Maher 1982; Dixon und Coles 1997; Ley, Van de Wiele und Van Eetvelde 2019).</p>
<div class="formula">P(Heim) = 1 − F(θ<sub>2</sub> − α·x), &nbsp; P(Remis) = F(θ<sub>2</sub> − α·x) − F(θ<sub>1</sub> − α·x), &nbsp;
P(Gast) = F(θ<sub>1</sub> − α·x), &nbsp; x = R<sub>H</sub> + H<sub>L</sub> − R<sub>A</sub></div>
<p>Erwartete Punkte: xP<sub>H</sub> = 3·P(Heim) + P(Remis). Die Schwellen θ werden je Kategorie geschätzt.</p>
{P.figur(f"Mechanik: Wahrscheinlichkeiten nach Elo-Differenz. Illustration mit Schwellen aus den beobachteten Häufigkeiten "
         f"(Remisband bei gleicher Stärke = {pz(BASE[1])}) und der klassischen Elo-Steigung α = ln 10/400 als Annahme; daraus folgt ein "
         f"Heimvorteil von rund {de(H_ELO)} Elo-Punkten. Mit wachsendem Abstand schrumpft zuerst das Remis, dann die Chance des Schwächeren.", fig_ologit())}
<p><strong>Bewertung.</strong> Rollierend außerhalb der Stichprobe mit RPS (Epstein 1969; Constantinou und Fenton 2012),
logarithmischem Score (Wheatcroft 2021), Brier-Score und Kalibrierung; Einzelheiten in Abschnitt 12.</p>
{P.kernaussage("Kernaussagen", ["Drei Modelle, eine Bewertung: geordnetes Logit, Davidson, Poisson.", "Erwartete Punkte je Spiel sind die Grundlage für M5."])}
""")

lo, hi = DEC[0][:, 1].mean(), DEC[-1][:, 1].mean()
P.abschnitt("m3", "Baustein M3: Kaderstärke der Startelf und Kombination", f"""
<p><strong>Idee.</strong> Arntzen und Hvattum (2021) zeigen, dass Elo und die Plus-Minus-Ratings der beiden Startelfen je für sich
etwa gleich gut prognostizieren, zusammen aber signifikant besser. M3 überträgt das auf das Unterhaus:</p>
<div class="formula">S<sub>T</sub>(m) = Σ<sub>i∈Startelf</sub>(β<sub>i</sub><sup>O</sup> + β<sub>i</sub><sup>D</sup>) − Ligamittel, &nbsp;
x = α<sub>1</sub>·(R<sub>H</sub> + H<sub>L</sub> − R<sub>A</sub>) + α<sub>2</sub>·(S<sub>H</sub> − S<sub>A</sub>)</div>
<p><strong>Gefrorene Ratings.</strong> Die Ratings müssen vor dem Spiel feststehen: je Saison aus allen früheren Spielen geschätzt.
Sonst enthielte S<sub>T</sub> das Ergebnis, das vorhergesagt wird. Test der Kombination mit einem gepaarten Test auf die RPS-Differenz
je Spiel.</p>
<p><strong>Vorprüfung.</strong> Mit den heutigen Ratings, also in der Stichprobe und deshalb ausdrücklich kein Prognosetest, steigt der
Heimsiegeranteil von {pz(lo, 0)} im Zehntel mit dem klar stärkeren Gast auf {pz(hi, 0)} im Zehntel mit der klar stärkeren Heimelf
({de(len(LU))} Spiele mit je mindestens neun bewerteten Startspielern). Die Richtung stimmt; wie viel davon außerhalb der Stichprobe
bleibt, beantwortet erst M3 mit gefrorenen Ratings.</p>
{P.figur("Ausgänge nach Differenz der Startelf-Ratings, in Zehnteln. Vorprüfung in der Stichprobe: die Ratings enthalten diese Spiele "
         "selbst und überschätzen deshalb die Trennschärfe. Sie zeigt nur, dass das Signal in die erwartete Richtung geht.", fig_lineup())}
<p><strong>Zerlegung.</strong> Aus R<sub>T</sub> = a + b·S<sub>T</sub> + u<sub>T</sub> über alle Mannschaftssaisonen: Anteil der
Mannschaftsstärke, den der Kader erklärt, und Mannschaftsmehrwert u<sub>T</sub>. Robustheit: Plus-Minus mit regularisiertem Term je
Mannschaft und Saison τ; stimmen τ und u<sub>T</sub> überein, ist der Mehrwert belastbar.</p>
{P.kernaussage("Kernaussagen", ["Hypothese: Elo plus Kaderstärke schlägt beide allein.", "Die Vorprüfung zeigt die richtige Richtung, ist aber kein Beleg.",
                                "Entscheidung 2 hängt an diesem Test."])}
""")

sh = {k: STATE[k]/max(1, sum(STATE.values())) for k in STATE}
P.abschnitt("m4", "Baustein M4: Punkte-Plus-Minus", f"""
<p><strong>Idee.</strong> Dieselbe Regression wie heute, aber jedes Tor zählt mit der Veränderung der erwarteten Punkte, die es
bewirkt (Kharrat, McHale und López Peña 2020). Die erwarteten Punkte im Spielverlauf kommen aus einem Poisson-Modell der restlichen
Tore, ohne Stärkeinformation (Abschnitt 5), mit den Torraten der Erwachsenen von {de(LAM_H, 2)} (Heim) und {de(LAM_A, 2)} (Gast) je
Spiel aus den Daten; die Schlussphase wird nach Robberechts, Van Haaren und Davis (2021) gesondert geprüft.</p>
<div class="formula">EP<sub>H</sub>(t, Δ) = 3·P(Heim vorne am Ende | t, Δ) + P(gleich | t, Δ), &nbsp;
y<sub>H</sub><sup>off</sup>(s) = Σ<sub>Tore Heim in s</sub> [EP<sub>H</sub>(nach) − EP<sub>H</sub>(vor)]</div>
{P.figur("Mechanik: Hebel eines Tores = erwartete Punkte nach eigenem minus nach gegnerischem Tor, je Spielstand und Minute. Beim "
         "Gleichstand wächst der Hebel bis zum Schluss; bei drei Toren Vorsprung ist er fast null. Genau diese Unterschiede ignoriert das "
         "Tor-Rating.", fig_hebel())}
<p>Wie viel davon betroffen ist, zeigen die Daten: {pz(sh.get(3, 0)+sh.get(2, 0))} aller Tore fallen bei zwei oder mehr Toren
Vorsprung der torschießenden Mannschaft, {pz(sh.get(-2, 0))} bei zwei oder mehr Toren Rückstand. Im Tor-Rating zählen sie voll, im
Punkte-Rating umso weniger, je später sie fallen.</p>
{P.figur("Tore nach Spielstand vor dem Tor. Grün: Tore beim Gleichstand, die den größten Hebel haben. Grau: Tore in weitgehend "
         "entschiedenen Spielständen.", fig_spielstand())}
<p><strong>Einheit</strong> Punkte pro 90 Minuten: +0,10 heißt rund drei Punkte mehr über 30 Spiele. Anschlussfähig an das Ligamodell
und an Strykerlabs Impact. <strong>Weg B</strong> als Prüfung: Tor-Rating mit Segmentgewicht w = Hebel/mittlerer Hebel.
<strong>Grenze:</strong> Spiele ohne Tor-Minuten fallen heraus und werden ausgewiesen.</p>
{P.kernaussage("Kernaussagen", ["Gleiche Regression, neue Zielgröße: Punkte statt Tore.",
                                f"{pz(sh.get(3, 0)+sh.get(2, 0))} der Tore fallen in entschiedenen Führungen; dort korrigiert M4 am stärksten."])}
""")

P.abschnitt("m5", "Baustein M5: Trainermodul", f"""
<p><strong>Idee.</strong> Je Amtszeit wird gemessen, ob die Mannschaft mehr Punkte holt, als Stärke und Aufstellung erwarten
lassen, ob sie stärker ist als die Summe ihrer Spieler und ob die Spieler besser werden. Logik und Prüfungen folgen dem
Trainer-Performance-Modell der Bundesliga; die Erwartung kommt hier aus M2 und M3 statt aus der Wettquote.</p>
<p><strong>Amtszeiten.</strong> Die Spielberichte nennen {de(len(COACHES))} Trainer. Je Mannschaft ergeben sich
{de(len(RAW[False])+len(RAW[True]))} Folgen desselben Trainers, davon {de(N1[False]+N1[True])} mit nur einem Spiel. Eine Folge von
höchstens zwei Spielen zwischen zwei Folgen desselben Trainers ist eine Vertretung und wird zugeschlagen
({de(N_SUB[False]+N_SUB[True])} Fälle).</p>
{P.figur("Länge der Trainerfolgen vor und nach Bereinigung der Vertretungen. Die Bereinigung verschiebt Masse von Einzelspielen zu "
         "langen Amtszeiten; ausgewertet werden nur Amtszeiten rechts der gestrichelten Linie.", fig_amtszeiten())}
{P.tabelle("Kennzahlen je Amtszeit mit mindestens 20 Spielen.", ["Kennzahl", "Rechnung", "Lesart"], [
 ["T1 Punkte über Erwartung", "Σ(Punkte − xP), z = Σ/(σ·√n)", "mehr Punkte, als Stärke und Aufstellung erwarten ließen"],
 ["T2 Mannschaftsmehrwert", "Mittel u<sub>T</sub> gegen Wert vor Amtsantritt", "stärker als die Summe der Spieler"],
 ["T3 kaderbereinigter Verlauf", "ΔR − b·ΔS", "Stärkezuwachs, der nicht aus Zugängen kommt"],
 ["T4 Spielerentwicklung", "Δ „Total akt.“ der Eingesetzten minus Alterserwartung", "Spieler werden besser als Gleichaltrige"],
 ["T5 Konsistenz", "Vorzeichen T1 in beiden Hälften", "Schutz gegen eine Glücksphase"]], "lll", breit=True)}
<p><strong>Wie viel sich messen lässt.</strong> Die Punkte je Spiel streuen um die Grunderwartung mit σ = {de(SIGMA, 2)}. Für einen
wahren Effekt von 0,2 Punkten je Spiel braucht man rund {de(n_power(0.2))} Spiele, für 0,3 rund {de(n_power(0.3))}.</p>
{P.figur("Nötige Spielzahl, um einen Trainereffekt mit 80 % Power zu erkennen, mit der Streuung um die Grunderwartung je Kategorie. "
         "Mit einer Erwartung aus Elo sinkt die Streuung etwas, an der Größenordnung ändert das wenig: Typische Amtszeiten reichen nur "
         "für große Effekte.", fig_power())}
<p><strong>Pflichtprüfungen</strong> vor jeder Trainerkennzahl: Split-Half-Reliabilität, Permutationstest, Korrelation desselben
Trainers bei verschiedenen Klubs ({de(N_MULTI_CLUB)} Trainer), Kontrolle der Mehrfachtests, Ereignisstudie mit Kontrollgruppe ohne
Wechsel (van Ours und van Tuijl 2016). Die Literatur findet überwiegend Rückkehr zum Mittelwert (ter Weel 2011; Muehlheusser,
Schneemann und Sliwka 2016; Bryson, Buraimo, Farnell und Simmons 2024); das Bundesliga-Modell kam auf Reliabilitäten von 0,05 bis 0,14.</p>
{P.kernaussage("Kernaussagen", [f"{de(N20[False])} Erwachsenen- und {de(N20[True])} Jugendamtszeiten mit ≥ 20 Spielen.",
                                "Trainereffekt nur bei T1, T2, T3 gleichgerichtet und bestandenen Prüfungen.",
                                "Kleine Effekte sind je Amtszeit nicht messbar; das ist ein Ergebnis, kein Mangel."])}
""")

P.abschnitt("mehrwert", "Zusammenspiel und Mehrwerte", f"""
{P.tabelle("Zusammenspiel der Bausteine.", ["Baustein", "braucht", "liefert an"], [
 ["M1 Team-Elo", "Ergebnisse, Datum, Bewerb", "M2, M3, M5, Dashboard, MCP"],
 ["M2 Wahrscheinlichkeiten", "M1", "M3, M5, Saisonsimulation"],
 ["M3 Kaderstärke", "M1, M2, gefrorene Ratings, Startelf", "M5, Prognose mit Aufstellung"],
 ["M4 Punkte-Plus-Minus", "Segmente, Tor-Minuten, Spielstandsmodell", "Scouting, Profile, Strykerlabs Impact"],
 ["M5 Trainer", "M1–M3, Trainer je Spiel, „Total akt.“", "Trainerprofil, Trainer-Performance"]], "lll")}
{P.figur("Mehrwert je Anwender und Baustein. Dunkelgrün: Hauptnutzen, hellgrün: Nebennutzen. Jeder Anwender braucht mindestens zwei "
         "Bausteine; M1 und M3 tragen am breitesten.", fig_matrix())}
<h3>Scouting</h3>
<ul class="grenzen">
<li><strong>Punkte statt Tore.</strong> Wer knappe Spiele entscheidet, steigt; wer in Kantersiegen trifft, fällt.</li>
<li><strong>Ligaabstand δ<sub>L</sub>.</strong> Was +0,20 in der Kärntner Liga gegenüber der Regionalliga Ost wert ist.</li>
<li><strong>Validierte Ratings.</strong> Sagt die Kaderstärke Ergebnisse vorher, ist belegt, dass die Ratings Leistung messen.</li>
</ul>
<h3>Klubs und Sportdirektion</h3>
<ul class="grenzen">
<li><strong>Wahrscheinlichkeiten je Spiel</strong> und erwartete Punkte: War die Niederlage Pech oder erwartbar?</li>
<li><strong>Saisonsimulation</strong> für Meister, Aufstieg und Abstieg jeder Landes- und Regionalliga, das Gegenstück zum Ligamodell.</li>
<li><strong>Aufstellungsabhängige Prognose:</strong> der Wert eines Spielers als Veränderung der Siegwahrscheinlichkeit.</li>
<li><strong>Kollektiv oder Einzelspieler:</strong> die Zerlegung zeigt, wie anfällig eine Mannschaft für Abgänge ist.</li>
</ul>
<h3>Trainerbewertung</h3>
<ul class="grenzen">
<li><strong>Erste objektive Trainerbewertung</strong> in Ligen ohne Quoten und xG.</li>
<li><strong>Trainerscouting</strong> für den Profibereich aus Regionalligen und Akademien, mit Panel über Klubwechsel.</li>
<li><strong>Entwicklungswirkung T4</strong>: für Akademien die eigentlich relevante Trainerqualität.</li>
</ul>
<h3>Verband, Nachwuchs, Produkt</h3>
<ul class="grenzen">
<li><strong>Ligaabstände und Jahrgänge</strong>: was der Schritt von der U18 in die Regionalliga im Mittel kostet.</li>
<li><strong>Lücke im Gesamtbild</strong>: Kontextring „Mannschaft“ gefüllt; neue MCP-Werkzeuge für Prognose, Teamrating und Trainerprofil.</li>
<li><strong>Wissenschaftlicher Beitrag</strong>: Prüfung von Arntzen und Hvattum (2021) im Amateur- und Jugendbereich; nach unserem Kenntnisstand nicht publiziert.</li>
</ul>
{P.kernaussage("Kernaussagen", ["Alle Mehrwerte sind Hypothesen bis zur jeweiligen Abnahme in Abschnitt 14."])}
""")

P.abschnitt("validierung", "Validierung", f"""
<p>Jede Prognose wird rollierend außerhalb der Stichprobe bewertet: Für Runde t wird nur mit Runden davor gerechnet. Maße: RPS als
Hauptmaß, logarithmischer Score, Brier-Score, Trefferquote und Kalibrierung (vorhergesagte gegen beobachtete Heimsiegquote in zehn
Klassen, Steigung einer logistischen Regression; 1 = kalibriert).</p>
{P.figur("Messlatten. Grau: einfache Regeln auf allen " + de(N_MR) + " Spielen; grün: die Häufigkeitsregel als Hauptmesslatte. "
         "* je Bewerb in der Stichprobe, daher etwas zu günstig. Dunkelgrün: Wettquoten der Bundesliga aus dem Trainer-Performance-"
         "Modell, nur als Größenordnung, andere Ligen.", fig_baseline())}
{P.tabelle("Abnahmekriterien der Validierung.", ["Prüfung", "Kriterium"], [
 ["F1 Prognosegüte M1/M2", f"RPS deutlich unter {de(RPS['Häufigkeit gesamt'], 3)}; Kalibrierungssteigung 0,9 bis 1,1 je Kategorie"],
 ["F2 Kombination M3", "RPS der Kombination signifikant unter Elo allein (gepaarter Test je Spiel)"],
 ["F3 Punkte-Plus-Minus", "Spielstandsmodell kalibriert; Abweichungen zum Tor-Rating fachlich plausibel"],
 ["F4 Trainer", "Reliabilität, Permutation, Klubwechsel und Kontrollgruppe berichtet, auch wenn negativ"],
 ["Wettmarkt (Stichprobe)", "Regionalligen mit beschaffbaren Schlussquoten: Abstand zum Markt ausweisen"]], "ll")}
{P.kernaussage("Kernaussagen", [f"Messlatte RPS {de(RPS['Häufigkeit gesamt'], 3)}.", "Keine Kennzahl ohne Test außerhalb der Stichprobe."])}
""")

P.abschnitt("grenzen", "Grenzen und offene Punkte", f"""
<ul class="grenzen">
<li><strong>Dünne Information.</strong> Ein Ausgang mit rund {de(HDA['gesamt'][4], 1)} Toren je Spiel; ohne Quoten und xG bleibt die
Güte unter Modellen der Bundesliga.</li>
<li><strong>Getrennte Ligagruppen.</strong> Ohne δ<sub>L</sub> sind Elo-Werte über Gruppen nicht vergleichbar; häufigster Bedienfehler.</li>
<li><strong>Jugend.</strong> Jährlicher Jahrgangswechsel; Elo trägt über die Saisongrenze kaum, die Kaderstärke schon.</li>
<li><strong>Vorgriff.</strong> Jede Prognosegröße muss vor dem Spiel feststehen, vor allem die Ratings in M3.</li>
<li><strong>Trainerdaten.</strong> Vertretungen, Spielertrainer, Namensvarianten; Bereinigung ist Voraussetzung.</li>
<li><strong>Selektion und kleine Stichproben.</strong> Entlassungen folgen schlechten Ergebnissen; je Amtszeit sind nur große Effekte messbar.</li>
<li><strong>Tor-Minuten.</strong> {de(N_GOALS_EV-n_goal_used)} Tor-Ereignisse ohne verwertbare Minute; die betroffenen Spiele fallen aus M4.</li>
</ul>
""")

P.abschnitt("plan", "Stand und nächste Schritte", f"""
{P.tabelle("Stand.", ["Teil", "Stand"], [
 ["Plus-Minus-Rating, zeitgewichtete Variante, Dashboard", "gebaut, lokal geprüft, nicht deployt"],
 ["Datenanalyse für dieses Papier (Ligagruppen, Amtszeiten, Messlatten)", "gebaut, im Generator"],
 ["M1 bis M5", "offen"]], "ll")}
{P.tabelle("Umsetzungsplan mit Abnahme (Aufwand: Schätzung in Arbeitstagen).", ["Phase", "Inhalt", "Abnahme", "Tage"], [
 ["P0 Datenaufbereitung", "Trainernamen, Amtszeiten mit Vertretungsregel, Mannschaftsnamen über Saisonen, Ligagruppen", "30 Amtszeiten gegen oefb.at geprüft, Fehler unter 5 %", "2–3"],
 ["P1 Team-Elo, Wahrscheinlichkeiten", "M1, M2, rollierende Bewertung, Pi-Rating und Poisson als Vergleich", f"RPS deutlich unter {de(RPS['Häufigkeit gesamt'], 3)}, Kalibrierung 0,9–1,1", "3–4"],
 ["<strong>Entscheidung 1</strong>", "Reicht die Prognosegüte für Anwendungen?", "", ""],
 ["P2 Ligaverknüpfung", "Plus-Minus mit Term je Bewerb und Saison, δ<sub>L</sub>", "plausibel zu Auf- und Abstieg, stabil bei Teilstichproben", "2–3"],
 ["P3 Kaderstärke, Kombination", "gefrorene Ratings, Kombinationsmodell, Zerlegung, Variante mit Mannschaftsterm", "Kombination signifikant besser als Elo allein", "3–4"],
 ["<strong>Entscheidung 2</strong>", "Tragen die Ratings Prognoseinformation? Wenn nein, erst Plus-Minus überarbeiten", "", ""],
 ["P4 Punkte-Plus-Minus", "Spielstandsmodell, EP-Zielgröße, Hebelgewichte", "Spielstandsmodell kalibriert", "3"],
 ["P5 Trainermodul", "T1–T5, Pflichtprüfungen, Ereignisstudie mit Kontrollgruppe", "alle Prüfungen berichtet", "4–5"],
 ["P6 Integration", "Tabellen in build_db.py, scout.json v4, Reiter „Mannschaften“ und „Trainer“, MCP-Werkzeuge", "Browserprüfung, alte Daten blenden neue Teile aus", "3–4"],
 ["P7 Validierungsbericht", "Ergebnisse zu F1–F4 als Fassung 3 dieses Papiers", "Durchsicht Fachseite", "2"]], "llll", breit=True)}
<p>Gesamt rund 22 bis 28 Arbeitstage. Deploy wie bisher: erst Daten hochladen, dann Code pushen.</p>
{P.figur("Ablauf der Umsetzung. Nach P1 und P3 wird entschieden, ob weitergebaut wird; erst Entscheidung 2 klärt, ob M4 und M5 auf "
         "Ratings stehen, die Ergebnisse vorhersagen.", fig_gantt())}
""")

P.literatur({
 "Methoden: Ratings, Wahrscheinlichkeiten, Bewertung": [
  ("Hvattum, L. M. und Arntzen, H. (2010).", "Using ELO ratings for match result prediction in association football. <i>International Journal of Forecasting</i> 26(3), 460–470. doi:10.1016/j.ijforecast.2009.10.002", "M1, M2"),
  ("Constantinou, A. C. und Fenton, N. E. (2013).", "Determining the level of ability of football teams by dynamic ratings based on the relative discrepancies in scores between adversaries. <i>Journal of Quantitative Analysis in Sports</i> 9(1), 37–50. doi:10.1515/jqas-2012-0036", "Pi-Rating als Vergleich in M1"),
  ("Lasek, J., Szlávik, Z. und Bhulai, S. (2013).", "The predictive power of ranking systems in association football. <i>International Journal of Applied Pattern Recognition</i> 1(1), 27–46.", "Elo als stärkstes Rankingsystem"),
  ("Maher, M. J. (1982).", "Modelling association football scores. <i>Statistica Neerlandica</i> 36(3), 109–118. doi:10.1111/j.1467-9574.1982.tb00782.x", "Poisson-Tormodell M2, M4"),
  ("Dixon, M. J. und Coles, S. G. (1997).", "Modelling association football scores and inefficiencies in the football betting market. <i>JRSS Series C</i> 46(2), 265–280. doi:10.1111/1467-9876.00065", "Zeitgewichtetes Tormodell M2"),
  ("Ley, C., Van de Wiele, T. und Van Eetvelde, H. (2019).", "Ranking soccer teams on the basis of their current strength: A comparison of maximum likelihood approaches. <i>Statistical Modelling</i> 19(1), 55–73.", "Halbwertszeit, Modellvergleich M2"),
  ("Davidson, R. R. (1970).", "On extending the Bradley-Terry model to accommodate ties in paired comparison experiments. <i>JASA</i> 65, 317–328. doi:10.1080/01621459.1970.10481082", "Remismodell M2"),
  ("Epstein, E. S. (1969).", "A scoring system for probability forecasts of ranked categories. <i>Journal of Applied Meteorology</i> 8, 985–987.", "RPS"),
  ("Constantinou, A. C. und Fenton, N. E. (2012).", "Solving the problem of inadequate scoring rules for assessing probabilistic football forecast models. <i>Journal of Quantitative Analysis in Sports</i> 8(1). doi:10.1515/1559-0410.1418", "RPS als Standard"),
  ("Wheatcroft, E. (2021).", "Evaluating probabilistic forecasts of football matches: The case against the ranked probability score. <i>Journal of Quantitative Analysis in Sports</i> 17(4), 273–287. doi:10.1515/jqas-2019-0089", "logarithmischer Score"),
  ("Štrumbelj, E. (2014).", "On determining probability forecasts from betting odds. <i>International Journal of Forecasting</i> 30(4), 934–943.", "Quoten in der Stichprobenprüfung"),
  ("Wunderlich, F. und Memmert, D. (2018).", "The betting odds rating system: Using soccer forecasts to forecast soccer. <i>PLOS ONE</i> 13(6), e0198668. doi:10.1371/journal.pone.0198668", "Quoten als Maßstab"),
  ("Dubitzky, W., Lopes, P., Davis, J. und Berrar, D. (2019).", "The Open International Soccer Database for machine learning. <i>Machine Learning</i> 108(1), 9–28. doi:10.1007/s10994-018-5726-0", "Prognose nur aus Ergebnissen"),
  ("Robberechts, P., Van Haaren, J. und Davis, J. (2021).", "A Bayesian approach to in-game win probability in soccer. <i>Proceedings KDD ’21</i>, 3512–3521.", "Spielstandsmodell M4")],
 "Fußball-Anwendung: Plus-Minus und Trainer": [
  ("Hvattum, L. M. (2019).", "A comprehensive review of plus-minus ratings for evaluating individual players in team sports. <i>International Journal of Computer Science in Sport</i> 18(1), 1–23. doi:10.2478/ijcss-2019-0001", "Überblick Plus-Minus"),
  ("Hvattum, L. M. (2020).", "Offensive and defensive plus-minus player ratings for soccer. <i>Applied Sciences</i> 10(20), 7345. doi:10.3390/app10207345", "Bestehendes Modell, Hebelgewichte"),
  ("Hvattum, L. M., Kriegl, M.-A. und Čulík, M. (2023).", "Identifying talent with plus-minus ratings in association football. In Y. Dominicy und C. Ley (Hrsg.), <i>Statistics Meets Sports</i>, 175–200. Cambridge Scholars.", "Peak-Rating, Talent-Perzentil"),
  ("Arntzen, H. und Hvattum, L. M. (2021).", "Predicting match outcomes in association football using team ratings and player ratings. <i>Statistical Modelling</i> 21(5), 449–470. doi:10.1177/1471082X20929881", "M3"),
  ("Kharrat, T., McHale, I. G. und López Peña, J. (2020).", "Plus-minus player ratings for soccer. <i>European Journal of Operational Research</i> 283(2), 726–736.", "M4"),
  ("Ilardi, S. (2007).", "Adjusted plus-minus: An idea whose time has come. 82games.com (nicht begutachtet).", "zwei Beobachtungen je Segment"),
  ("ter Weel, B. (2011).", "Does manager turnover improve firm performance? Evidence from Dutch soccer, 1986–2004. <i>De Economist</i> 159(3), 279–303.", "M5"),
  ("van Ours, J. C. und van Tuijl, M. A. (2016).", "In-season head-coach dismissals and the performance of professional football teams. <i>Economic Inquiry</i> 54(1), 591–604.", "M5, Kontrollgruppe"),
  ("Muehlheusser, G., Schneemann, S. und Sliwka, D. (2016).", "The impact of managerial change on performance: The role of team heterogeneity. <i>Economic Inquiry</i> 54(2), 1128–1149. doi:10.1111/ecin.12285", "M5, Selektion"),
  ("Bryson, A., Buraimo, B., Farnell, A. und Simmons, R. (2024).", "Special ones? The effect of head coaches on football team performance. <i>Scottish Journal of Political Economy</i> 71(3), 295–322.", "M5")],
 "Datenquellen und interne Dokumente": [
  ("ÖFB, oefb.at.", "Spielberichte (Druckansicht) und Spielerprofile, gescrapt mit oefb_scraper.py; Stand der Datenbank wie in Tabelle 3.", "alle Bausteine"),
  ("Strykerlabs (2026).", "Trainer-Performance-Modell: Methodik und Übertragung auf andere Ligen, 03.11.2026.", "M5, Referenz-RPS"),
  ("Strykerlabs (2026).", "ÖFB-Plus-Minus: plusminus.py und DASHBOARD-DATA.md im Projekt ~/claude.", "Abschnitt 4")]})

P.abschnitt("formeln", "Notation", """<dl class="formeln">
<dt>β<sub>i</sub><sup>O</sup>, β<sub>i</sub><sup>D</sup></dt><dd>Offensiv- und Defensivrating von Spieler i, Tore pro 90 Minuten.</dd>
<dt>λ, w</dt><dd>Regularisierungsstärke; Segmentgewicht (Zeit oder Spielstand).</dd>
<dt>R<sub>T</sub>, H<sub>L</sub>, K, γ, ρ</dt><dd>Elo-Stärke, Heimvorteil je Kategorie oder Bewerb, Lernrate, Dämpfung der Tordifferenz, Rückzug zum Mittel.</dd>
<dt>δ<sub>L</sub></dt><dd>Niveauabstand von Bewerb L.</dd>
<dt>S<sub>T</sub>, u<sub>T</sub>, τ</dt><dd>Kaderstärke der Startelf; Mannschaftsmehrwert; Mannschaftsterm der Robustheitsvariante.</dd>
<dt>EP, xP</dt><dd>Erwartete Punkte im Spielverlauf; erwartete Punkte vor dem Spiel.</dd>
<dt>RPS</dt><dd>Ranked Probability Score, kleiner ist besser.</dd></dl>""", anhang=True)

P.abschnitt("dateien", "Datei- und Skriptverzeichnis", P.tabelle("Dateien.", ["Datei", "Stand", "Inhalt"], [
 ["plusminus.py", "gebaut", "Plus-Minus, zeitgewichtete Variante, ratings_meta.json"],
 ["build_db.py, build_dashboard.py", "gebaut", "SQLite, scout.json, Profile"],
 ["docs/methodik/gen_methodenpapier.py", "gebaut", "dieses Papier, alle Zahlen und Grafiken"],
 ["coaches.py", "geplant (P0, M5)", "Amtszeiten, Trainerkennzahlen"],
 ["team_elo.py", "geplant (P1)", "M1, M2"],
 ["lineup_strength.py", "geplant (P3)", "M3, Zerlegung"],
 ["plusminus.py --target ep", "geplant (P4)", "M4"]], "lll"), anhang=True)

P.abschnitt("herleitung", "Herleitung der Kennzahlen", f"""<p>Ligagruppen über Mannschaften: zwei Bewerbe verbunden, wenn eine
Mannschaft unter gleichem Namen in beiden gespielt hat; über Spieler: wenn ein Spieler mit Minuten in beiden eingesetzt wurde.
Kategorie Jugend: Bewerbsname enthält „U“ mit Ziffer oder „Jugend“. Trainerfolgen je Mannschaft und Kategorie nach Datum,
Trainername wie im Spielbericht. RPS der Regeln auf allen {de(N_MR)} Spielen mit Endstand. σ der Punkte: Standardabweichung von
Punkten minus Grunderwartung je Kategorie und Spielseite ({de(len(res))} Mannschaftsspiele). Power: n = (2,8·σ/δ)². Hebel: Poisson
der restlichen Tore mit den Torraten der Erwachsenen, unabhängig je Mannschaft.</p>""", anhang=True)

stem = f"Mannschaftsstaerke_Methodenpapier_Fassung{FASSUNG}_{HEUTE.isoformat()}"
h = P.html(HERE/f"{stem}.html"); print("->", P.pdf(HERE/f"{stem}.pdf", h))
