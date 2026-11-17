# -*- coding: utf-8 -*-
"""Paper zum Scouting-Dashboard: Aufbau, Methode, Verbindung Spielerwert -> Gewinnwahrscheinlichkeit, Validierungsstudie.

Ein Generator, zwei Fassungen:
    python3 docs/paper/gen_dashboard_paper.py            -> interne Fassung (mit Einordnung und Dateiverweisen)
    python3 docs/paper/gen_dashboard_paper.py extern     -> externe Fassung (ohne Einordnung, ohne interne Spuren)
    python3 docs/paper/gen_dashboard_paper.py extern en  -> externe Fassung auf Englisch
Grundsatz fuer alle Paper: Die Zusammenfassung beginnt mit dem Nutzen (was bringt es, was ist es wert), erst danach Methode.
Zahlen kommen aus validierung/studie_ergebnis.json (validierung/studie.py) und data/matches.csv.
"""
import csv, json, re, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/strykerlabs-paper/scripts"))
sys.path.insert(0, str(Path.home() / ".claude/skills/strykerlabs-paper-extern/scripts"))
from paper import Paper
from paper_extern import PaperExtern
from figstyle import plt, svg, GREEN, CA, CB, CC, INK, MUTE, GRAU, HELLGRAU
from figstyle import de as _de
from matplotlib.patches import FancyBboxPatch

EXTERN = "extern" in sys.argv[1:]
EN = "en" in sys.argv[1:]                       # englische Fassung: python3 gen_dashboard_paper.py extern en
TX = lambda d, e: e if EN else d
ROOT = Path(__file__).resolve().parents[2]
S = json.loads((ROOT / "validierung" / "studie_ergebnis.json").read_text(encoding="utf-8"))
T1, T2 = S["talent"]; B = S["prognose"]; D = S["daten"]
STAND = "17.11.2026"; FASSUNG = "1"
YOUTH = re.compile(r"\bU\s?\d|jugend", re.I)

# ---------------------------------------------------------------- Daten fuer die Uebersichtsgrafik
def _season(d):
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", d or "")
    if not m: return None
    y, mo = int(m.group(3)), int(m.group(2)); a = y if mo >= 7 else y - 1
    return f"{a}/{str(a + 1)[2:]}"
SE = Counter(); SJ = Counter()
for r in csv.DictReader(open(ROOT / "data" / "matches.csv", encoding="utf-8")):
    s = _season(r["date"])
    if s: (SJ if YOUTH.search(r["competition"]) else SE)[s] += 1
SEASONS = sorted(set(SE) | set(SJ))
SC = json.loads((ROOT / "data" / "scout.json").read_text(encoding="utf-8"))["stats"]
N_SPIELER, N_RATING, N_SPIELE = SC["players_with_id"], SC["ratings"], SC["matches"]

# ---------------------------------------------------------------- Grafik-Helfer
def box(ax, x, y, w, h, t, sub="", fc=HELLGRAU, tc=INK, ec="none", fs=8.4):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=1.0", fc=fc, ec=ec, lw=1.3))
    ax.text(x + w / 2, y + h * (0.64 if sub else 0.5), t, ha="center", va="center", color=tc, fontsize=fs, fontweight="bold")
    if sub: ax.text(x + w / 2, y + h * 0.28, sub, ha="center", va="center", color=tc, fontsize=6.4, linespacing=1.2)
def arrow(ax, a, b, c="#888", lw=1.0, ls="-"):
    ax.annotate("", b, a, arrowprops=dict(arrowstyle="-|>", color=c, lw=lw, ls=ls, mutation_scale=9, shrinkA=0, shrinkB=0))
de = lambda x, d=0: (f"{x:,.{d}f}" if EN else _de(x, d))          # Zahl in der Schreibweise der Sprache
pct = lambda v, d=0: de(v, d) + ("%" if EN else " %")

def fig_aufbau():
    fig, ax = plt.subplots(figsize=(8.2, 3.3)); ax.set_axis_off(); ax.set_xlim(0, 100); ax.set_ylim(0, 42)
    for x, t in [(1, TX("Daten", "Data")), (26, TX("Modell", "Model")), (52, "Dashboard"), (80, TX("Entscheidung", "Decision"))]: ax.text(x, 40.5, t, fontsize=8, color=MUTE)
    box(ax, 1, 26, 19, 11, TX("Ergebnisse", "Results"), TX("Endstand je Spiel", "final score per match"))
    box(ax, 1, 13.5, 19, 11, TX("Aufstellungen", "Line-ups"), TX("wer spielte wann", "who played when"))
    box(ax, 1, 1, 19, 11, TX("Tor-Minuten", "Goal minutes"), TX("wann fiel welches Tor", "when each goal was scored"))
    box(ax, 26, 20, 20, 13, TX("Spielerwert", "Player value"), TX("Plus-Minus, bereinigt um\nMitspieler und Gegner", "plus-minus, adjusted for\nteammates and opponents"), fc=CA, tc="white")
    box(ax, 26, 4, 20, 13, TX("Mannschaftsstärke", "Team strength"), TX("Startelf-Summe und\nErgebnisverlauf", "line-up total and\nresults history"), fc=CA, tc="white")
    for y, t, s_ in [(29, "Scouting", TX("Filter, Vorlagen, Rangliste", "filters, presets, ranking")), (19.5, TX("Spielerprofil", "Player profile"), TX("drei Fragen, ein Urteil", "three questions, one verdict")),
                     (10, TX("Teams und Statistik", "Teams and statistics"), TX("Kader, Alter, Einsatz Junger", "squads, age, minutes for youngsters")), (0.5, TX("Spiele", "Matches"), TX("Aufstellungen, Ereignisse", "line-ups, events"))]:
        box(ax, 52, y, 22, 8, t, s_, fc=GREEN, tc="white", fs=7.8)
    box(ax, 80, 26, 19, 11, TX("Verpflichten", "Sign"), TX("wen beobachten,\nwen holen", "whom to watch,\nwhom to sign"), fc="white", ec=GREEN)
    box(ax, 80, 13.5, 19, 11, TX("Fördern", "Develop"), TX("wer ist bereit für\nden nächsten Schritt", "who is ready for\nthe next step"), fc="white", ec=GREEN)
    box(ax, 80, 1, 19, 11, TX("Einordnen", "Assess"), TX("wie stark ist ein\nTeam wirklich", "how strong a team\nreally is"), fc="white", ec=GREEN)
    for y in (31.5, 19, 6.5): arrow(ax, (20.4, y), (25.6, 26.5 if y > 10 else 10.5))
    for y in (33, 23.5, 14, 4.5): arrow(ax, (46.4, 26.5 if y > 15 else 10.5), (51.6, y))
    for y0, y1 in [(33, 31.5), (23.5, 19), (14, 6.5)]: arrow(ax, (74.4, y0), (79.6, y1))
    return svg(fig)

def fig_daten():
    fig, ax = plt.subplots(figsize=(7.4, 2.6))
    e = [SE[s] for s in SEASONS]; j = [SJ[s] for s in SEASONS]
    ax.bar(SEASONS, e, color=CA, width=.6, label=TX("Erwachsenenfußball", "Senior football")); ax.bar(SEASONS, j, bottom=e, color=GREEN, width=.6, label=TX("Nachwuchs", "Youth"))
    for i in range(len(SEASONS)): ax.text(i, e[i] + j[i] + 70, de(e[i] + j[i]), ha="center", fontsize=8)
    ax.set_ylabel(TX("ausgewertete Spiele", "matches analysed")); ax.set_ylim(0, max(a + b for a, b in zip(e, j)) * 1.18); ax.legend(loc="upper left", fontsize=7.5, ncol=2)
    ax.text(len(SEASONS) - 1, -0.16 * ax.get_ylim()[1], TX("laufende Saison", "current season"), ha="center", fontsize=7, color=MUTE)
    return svg(fig)

def fig_segmente():
    fig, ax = plt.subplots(figsize=(7.6, 2.5)); ax.set_axis_off(); ax.set_xlim(-12, 100); ax.set_ylim(0, 30)
    X = lambda m: m / 90 * 96
    for a, b_, t, c in [(0, 58, TX("Abschnitt 1: 0. bis 58. Minute", "Segment 1: minute 0 to 58"), "#eef5f2"), (58, 90, TX("Abschnitt 2: 58. bis 90. Minute", "Segment 2: minute 58 to 90"), "#e3efe9")]:
        ax.add_patch(FancyBboxPatch((X(a) + .4, 4), X(b_) - X(a) - .8, 20, boxstyle="round,pad=0.1,rounding_size=0.8", fc=c, ec="#cfd8d4", lw=.8))
        ax.text((X(a) + X(b_)) / 2, 26.5, t, ha="center", fontsize=7.6, color=MUTE)
    ax.text(-11, 18, TX("Heim", "Home"), fontsize=8.4, fontweight="bold"); ax.text(-11, 9, TX("Gast", "Away"), fontsize=8.4, fontweight="bold")
    for x_, y_, t in [(X(29), 18, TX("Spieler A, B, C …", "players A, B, C …")), (X(74), 18, TX("A, B und der Neue D", "A, B and newcomer D")), (X(29), 9, TX("elf Gegenspieler", "eleven opponents")), (X(74), 9, TX("elf Gegenspieler", "eleven opponents"))]:
        ax.text(x_, y_, t, ha="center", va="center", fontsize=7.8, bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="#b9c4bf", lw=.8))
    ax.plot([X(58), X(58)], [3, 25], color=CB, lw=1.3, ls=(0, (4, 3))); ax.text(X(58), 1, TX("Wechsel: C geht, D kommt", "Substitution: C off, D on"), ha="center", fontsize=7.4, color=CB)
    for m_, y_ in [(23, 21.6), (71, 21.6), (80, 12.6)]: ax.text(X(m_), y_, TX("Tor", "Goal"), ha="center", fontsize=7, color="white", bbox=dict(boxstyle="round,pad=0.25", fc=GREEN, ec="none"))
    return svg(fig)

def fig_kette():
    fig, ax = plt.subplots(figsize=(8.2, 3.2)); ax.set_axis_off(); ax.set_xlim(0, 100); ax.set_ylim(0, 40)
    ax.text(1, 37.5, TX("Profifußball: von oben, über den Markt", "Professional football: top-down, via the market"), fontsize=8, color=MUTE)
    box(ax, 1, 25, 21, 9.5, TX("Wettquoten", "Betting odds"), TX("viele Marktteilnehmer", "many market participants"))
    box(ax, 39, 25, 22, 9.5, TX("Gewinnwahrscheinlichkeit", "Win probability"), TX("je Spiel", "per match"), fc=GREEN, tc="white", fs=8)
    box(ax, 78, 25, 21, 9.5, TX("erwartete Punkte", "Expected points"), TX("je Spiel und Saison", "per match and season"), fc="white", ec=GREEN)
    arrow(ax, (22.4, 29.7), (38.6, 29.7)); arrow(ax, (61.4, 29.7), (77.6, 29.7))
    ax.text(30.5, 31.3, TX("Quote umrechnen", "convert the odds"), ha="center", fontsize=6.6, color=MUTE)
    ax.text(1, 19.5, TX("Unterhalb der Profiligen: von unten, über die Spieler", "Below the professional leagues: bottom-up, via the players"), fontsize=8, color=MUTE)
    box(ax, 1, 4, 16, 11, TX("Spielerwerte", "Player values"), TX("Tore je 90 Minuten", "goals per 90 minutes"), fc=CA, tc="white")
    box(ax, 21, 4, 16, 11, TX("Startelf-Stärke", "Line-up strength"), TX("Summe der elf Werte", "sum of the eleven values"), fc=CA, tc="white")
    box(ax, 41, 4, 18, 11, TX("Tordifferenz", "Goal difference"), TX("erwartet, je Spiel", "expected, per match"), fc=CA, tc="white")
    box(ax, 63, 4, 16, 11, TX("Sieg, Remis,\nNiederlage", "Win, draw,\nloss"), "", fc=GREEN, tc="white", fs=7.6)
    box(ax, 83, 4, 16, 11, TX("Punkte", "Points"), TX("je Spiel und Saison", "per match and season"), fc="white", ec=GREEN)
    for a_, b_ in [(17.4, 20.6), (37.4, 40.6), (59.4, 62.6), (79.4, 82.6)]: arrow(ax, (a_, 9.5), (b_, 9.5))
    arrow(ax, (50, 24.4), (68, 15.6), c=GREEN, ls=(0, (3, 2))); ax.text(61.5, 20.6, TX("dieselbe Größe", "the same quantity"), fontsize=6.8, color=GREEN, ha="left")
    return svg(fig)

def fig_fuenftel():
    Q = B["fuenftel"]; fig, ax = plt.subplots(figsize=(7.4, 3.0))
    lab = TX(["klar schwächer", "etwas schwächer", "etwa gleich", "etwas stärker", "klar stärker"], ["clearly weaker", "slightly weaker", "about equal", "slightly stronger", "clearly stronger"])
    h = [q["heim"] for q in Q]; r_ = [q["remis"] for q in Q]; g = [q["gast"] for q in Q]; x = range(5)
    ax.bar(x, h, color=GREEN, width=.62, label=TX("Heimsieg", "Home win")); ax.bar(x, r_, bottom=h, color=GRAU, width=.62, label=TX("Remis", "Draw"))
    ax.bar(x, g, bottom=[a + b_ for a, b_ in zip(h, r_)], color=CB, width=.62, label=TX("Auswärtssieg", "Away win"))
    for i, q in enumerate(Q):
        ax.text(i, h[i] / 2, pct(h[i]), ha="center", va="center", color="white", fontsize=8.5, fontweight="bold")
        ax.text(i, 104, f"{de(q['ppg'], 2)} " + TX("Punkte", "points"), ha="center", fontsize=8)
    ax.set_xticks(list(x)); ax.set_xticklabels(lab); ax.set_ylim(0, 116); ax.set_yticks([0, 25, 50, 75, 100]); ax.set_ylabel(TX("Anteil der Spiele in %", "share of matches in %"))
    ax.set_xlabel(TX("Startelf der Heimmannschaft im Vergleich zum Gegner, nach Spielerwerten vor Saisonbeginn", "Home line-up compared with the opponent, by player values from before the season"))
    ax.legend(loc="upper center", bbox_to_anchor=(.5, -0.24), ncol=3, fontsize=7.5)
    return svg(fig)

def fig_rps():
    E = B["test_erwachsene"]; J = B["test_jugend"]
    keys = ["Häufigkeitsregel", "Startelf-Stärke (Spieler-Ratings), Stand Stichtag", "Mannschaftsstärke, Stand Stichtag",
            "Mannschaftsstärke laufend (Team-Elo)", "Startelf-Stärke + Mannschaftsstärke laufend"]
    lab = TX(["einfache Regel\n(immer gleiche Quote)", "Spielerwerte\n(Stand vor der Saison)", "Mannschaftsstärke\n(Stand vor der Saison)",
              "Mannschaftsstärke\n(laufend aktualisiert)", "Spielerwerte +\nMannschaftsstärke"],
             ["simple rule\n(always the same odds)", "player values\n(as of pre-season)", "team strength\n(as of pre-season)",
              "team strength\n(updated continuously)", "player values +\nteam strength"])
    col = [GRAU, CA, "#7aa5d6", "#7aa5d6", GREEN]
    fig, axs = plt.subplots(1, 2, figsize=(8.0, 3.0), sharey=False)
    for ax, R_, t, n in ((axs[0], E, TX("Erwachsenenfußball", "Senior football"), B["n_test_erw"]), (axs[1], J, TX("Nachwuchs", "Youth"), B["n_test_jug"])):
        v = [R_[k]["rps"] for k in keys]; ax.barh(range(5), v, color=col, height=.62); ax.invert_yaxis()
        for i, x_ in enumerate(v): ax.text(x_ + .0006, i, de(x_, 4), va="center", fontsize=7.8)
        ax.set_yticks(range(5)); ax.set_yticklabels(lab if ax is axs[0] else [""] * 5, fontsize=7.4); ax.set_xlim(min(v) - .012, max(v) + .008)
        ax.set_title(f"{t} · {de(n)} " + TX("Spiele der Saison 2026/27", "matches of season 2026/27")); ax.set_xlabel(TX("Prognosefehler (kleiner ist besser)", "forecast error (smaller is better)")); ax.grid(axis="y", visible=False)
    fig.tight_layout()
    return svg(fig)

def fig_spielerwert():
    W = B["spielerwert"]["stufen"]; fig, ax = plt.subplots(figsize=(7.4, 2.6))
    x = [f"+{de(w['delta'], 2)}" for w in W]; v = [w["punkte_30"] for w in W]
    ax.bar(x, v, color=GREEN, width=.55)
    for i, w in enumerate(W): ax.text(i, v[i] + .15, TX(f"+{de(v[i], 1)} Punkte\nSiegchance +{de(w['siegchance_pp'], 1)} PP", f"+{de(v[i], 1)} points\nwin chance +{de(w['siegchance_pp'], 1)} pp"), ha="center", fontsize=7.6, linespacing=1.3)
    ax.set_ylim(0, max(v) * 1.45); ax.set_xlim(-.6, len(W) - .4); ax.set_ylabel(TX("zusätzliche Punkte in 30 Spielen", "extra points in 30 matches")); ax.set_xlabel(TX("Verbesserung der Startelf in Toren je 90 Minuten (Summe der Spielerwerte)", "Improvement of the line-up in goals per 90 minutes (sum of player values)"))
    return svg(fig)

def fig_talent():
    fig, axs = plt.subplots(1, 2, figsize=(8.0, 3.1), sharey=True)
    for ax, T in zip(axs, (T1, T2)):
        tb = {b_["band"]: b_ for b_ in T["nach_talent"]}; mb = {b_["band"]: b_ for b_ in T["nach_minuten"]}
        bands = ["Top 2 %", "Top 10 %", "Top 20 %", "20 bis 50 %", "untere Hälfte"]; x = range(len(bands)); w = .38
        v = [tb[k]["quote"] for k in bands]; m_ = [mb[k]["quote"] for k in bands]
        lo = [v[i] - tb[k]["ci"][0] for i, k in enumerate(bands)]; hi = [tb[k]["ci"][1] - v[i] for i, k in enumerate(bands)]
        ax.bar([i - w / 2 for i in x], v, w, color=GREEN, label=TX("nach Talent-Rang", "by talent rank"), yerr=[lo, hi], error_kw=dict(ecolor="#555", lw=.8, capsize=2))
        ax.bar([i + w / 2 for i in x], m_, w, color=GRAU, label=TX("nur nach Einsatzminuten", "by minutes played only"))
        for i in x: ax.text(i - w / 2, 2.5, pct(v[i]), ha="center", fontsize=7.4, color="white", fontweight="bold", rotation=90, va="bottom")
        ax.axhline(T["basisquote"], color=CB, lw=1.1, ls=(0, (4, 3))); ax.text(len(bands) - .45, 91, TX("gestrichelt: Durchschnitt ", "dashed: average ") + pct(T['basisquote'], 1), ha="right", fontsize=7.2, color=CB)
        ax.set_xticks(list(x)); ax.set_xticklabels(TX(["Top\n2 %", "Top\n10 %", "Top\n20 %", "20 bis\n50 %", "untere\nHälfte"], ["top\n2%", "top\n10%", "top\n20%", "20 to\n50%", "bottom\nhalf"]), fontsize=7.6); ax.set_ylim(0, 100)
        ax.set_title(TX(f"{T['label']}: {de(T['n'])} Spieler, Jahrgänge {T['jahrgaenge'][0]} bis {T['jahrgaenge'][1]}", f"{T['label'].replace('Fenster', 'Window')}: {de(T['n'])} players, born {T['jahrgaenge'][0]} to {T['jahrgaenge'][1]}"))
    axs[0].set_ylabel(TX("Anteil mit Durchbruch in %", "share with breakthrough in %")); axs[0].legend(loc="upper right", bbox_to_anchor=(1, .9), fontsize=7.4)
    fig.tight_layout()
    return svg(fig)

def fig_topn():
    fig, axs = plt.subplots(1, 2, figsize=(8.0, 2.6), sharey=True)
    for ax, T in zip(axs, (T1, T2)):
        n = [t["n"] for t in T["topn"]]; pr = [100 * t["profi"] / t["n"] for t in T["topn"]]; rl = [100 * (t["treffer"] - t["profi"]) / t["n"] for t in T["topn"]]
        x = range(len(n)); ax.bar(x, pr, color=GREEN, width=.6, label=TX("Profiliga", "professional league")); ax.bar(x, rl, bottom=pr, color=CA, width=.6, label=TX("Stammspieler Regionalliga", "regular in the third tier"))
        for i, t in enumerate(T["topn"]): ax.text(i, pr[i] + rl[i] + 2.5, f"{t['treffer']} {TX('von', 'of')} {t['n']}", ha="center", fontsize=8)
        ax.axhline(T["basisquote"], color=CB, lw=1.1, ls=(0, (4, 3)))
        ax.set_xticks(list(x)); ax.set_xticklabels([TX(f"beste {k}", f"top {k}") for k in n]); ax.set_ylim(0, 108); ax.set_title(TX(T["label"], T["label"].replace("Fenster", "Window")))
    axs[0].set_ylabel(TX("Anteil mit Durchbruch in %", "share with breakthrough in %")); axs[1].legend(loc="upper right", fontsize=7.4)
    fig.tight_layout()
    return svg(fig)

def fig_abdeckung():
    fig, ax = plt.subplots(figsize=(7.6, 2.9)); ax.set_axis_off(); ax.set_xlim(0, 100); ax.set_ylim(0, 36)
    rows = [(TX("Bundesliga, 2. Liga", "Bundesliga, 2. Liga (tiers 1–2)"), 28, 30, True), (TX("Regionalligen", "Regionalliga (tier 3)"), 36, 23, False), (TX("Landesligen, Oberligen", "Landesliga, Oberliga (tiers 4–5)"), 50, 16, False), (TX("Akademie- und Nachwuchsligen", "Academy and youth leagues"), 64, 9, False)]
    for t, w, y, ev in rows:
        x0 = 30 - w / 2 + 6
        ax.add_patch(FancyBboxPatch((x0, y), w, 5.4, boxstyle="round,pad=0.15,rounding_size=0.7", fc=(HELLGRAU if ev else GREEN), ec="none"))
        ax.text(x0 + w / 2, y + 2.7, t, ha="center", va="center", fontsize=7.8, color=(INK if ev else "white"), fontweight="bold")
    ax.text(76, 32.7, TX("Eventdaten üblich,\nWettmarkt vorhanden", "event data common,\nbetting market exists"), fontsize=7.6, color=MUTE, va="center")
    ax.text(76, 17, TX("keine Eventdaten, kein Wettmarkt.\nSpielberichte liegen für jedes Spiel vor:\nErgebnis, Aufstellung, Wechsel, Tore.\nHier arbeitet das Dashboard.", "no event data, no betting market.\nMatch reports exist for every match:\nresult, line-up, substitutions, goals.\nThis is where the dashboard works."), fontsize=7.6, color=INK, va="center", linespacing=1.4)
    ax.plot([72, 72], [9, 28.4], color=GREEN, lw=2); ax.plot([72, 72], [30, 35.4], color=GRAU, lw=2)
    return svg(fig)

# ---------------------------------------------------------------- Paper
import paper as _paper

class PaperEN(PaperExtern):
    """Englische externe Fassung: gleiche Bausteine, feste Beschriftungen des Hauslayouts uebersetzt."""
    SUB = [('<span class="lab">Abbildung ', '<span class="lab">Figure '), ('<span class="lab">Tabelle ', '<span class="lab">Table '),
           ("<h2>Zusammenfassung</h2>", "<h2>Management summary</h2>"), ("<h2>Inhalt</h2>", "<h2>Contents</h2>"),
           ("Autor: ", "Author: "), ("Herausgeber: ", "Publisher: "), (", Fassung ", ", version "), ("· extern</p>", "· external</p>")]
    def literatur(self, gruppen):
        gruppen = dict(gruppen)
        gruppen["Own calculations"] = [("Strykerlabs Football Intelligence Hub (2026).", "Own calculations and simulations based on match data.", "all figures in this document")]
        out = "".join(f"<h3>{g}</h3><ul class='lit'>" + "".join(f"<li><strong>{a}</strong> {t} <em>— {w}</em></li>" for a, t, w in e) + "</ul>" for g, e in gruppen.items())
        return self.abschnitt("literatur", "References and sources", "<p>For each work, the use in this paper is stated.</p>" + out)
    def _body(self):
        b = super()._body()
        for a_, b_ in self.SUB: b = b.replace(a_, b_)
        return b
    def pdf(self, pfad, html_pfad=None):
        import base64
        from playwright.sync_api import sync_playwright
        html_pfad = Path(html_pfad) if html_pfad else Path(pfad).with_suffix(".html")
        logo = "data:image/png;base64," + base64.b64encode((_paper.SKILL / "assets/logo_wordmark.png").read_bytes()).decode()
        F = "font-family:Helvetica,Arial,sans-serif;font-size:7.5pt;color:#6b6b6b;"
        headt = (f'<div style="{F}width:100%;margin:0 16mm;padding-bottom:3mm;border-bottom:0.6pt solid {GREEN};display:flex;justify-content:space-between;align-items:flex-end">'
                 f'<img src="{logo}" style="height:6mm"><span style="letter-spacing:.08em;text-transform:uppercase;text-align:right">{_paper.REIHE}<br>{self.kurztitel} · Study, version {self.fassung}</span></div>')
        foot = (f'<div style="{F}width:100%;margin:0 16mm;padding-top:2.5mm;border-top:0.6pt solid #BFBFBF;display:flex;justify-content:space-between">'
                f'<span>{_paper.FIRMA}</span><span>Strykerlabs Football Intelligence Hub · {self.stand} · external</span>'
                '<span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>')
        with sync_playwright() as pw:
            try: b = pw.chromium.launch(channel="chrome")
            except Exception: b = pw.chromium.launch()
            pg = b.new_page(); pg.goto(html_pfad.resolve().as_uri(), wait_until="networkidle"); pg.emulate_media(media="print")
            pg.pdf(path=str(pfad), format="A4", print_background=True, display_header_footer=True, header_template=headt, footer_template=foot,
                   margin=dict(top="26mm", bottom="20mm", left="16mm", right="16mm"))
            b.close()
        return Path(pfad)

def kacheln(eintraege):
    """Nutzen auf einen Blick: vier Kacheln mit grosser Zahl und einem Satz (steht ganz oben in der Zusammenfassung)."""
    z = "".join(f'<td style="width:25%;vertical-align:top;padding:10px 12px;border:1px solid #d9d9d9;border-top:3px solid {GREEN}">'
                f'<div style="font-size:19pt;font-weight:700;color:{GREEN};line-height:1.1;font-family:Helvetica,Arial,sans-serif">{g}</div>'
                f'<div style="font-size:8.6pt;line-height:1.35;margin-top:5px;font-family:Helvetica,Arial,sans-serif">{t}</div></td>' for g, t in eintraege)
    return f'<table style="width:100%;border-collapse:separate;border-spacing:6px 0;margin:4px -6px 12px"><tr>{z}</tr></table>'

TITEL = TX("Bessere Spieler finden, wo es keine Eventdaten gibt", "Finding better players where no event data exists")
UNTER = TX("Das Scouting-Dashboard für den österreichischen Amateur- und Nachwuchsfußball: Nutzen, Aufbau, Methode und Nachweis der Aussagekraft",
           "The scouting dashboard for Austrian amateur and youth football: value, structure, method and evidence")
KURZ = TX("Scouting-Dashboard Amateur- und Nachwuchsfußball", "Scouting dashboard, amateur and youth football")
if EN:
    P = PaperEN(titel=TITEL, untertitel=UNTER, dokumenttyp="Study", fassung=FASSUNG, stand=STAND, kurztitel=KURZ)
elif EXTERN:
    P = PaperExtern(titel=TITEL, untertitel=UNTER, dokumenttyp="Studie", fassung=FASSUNG, stand=STAND, kurztitel=KURZ)
else:
    P = Paper(titel=TITEL, untertitel=UNTER, dokumenttyp="Studie", fassung=FASSUNG, stand=STAND, modul="oefb", kurztitel=KURZ)

t2 = {b_["band"]: b_ for b_ in T1["nach_talent"]}; t2b = {b_["band"]: b_ for b_ in T2["nach_talent"]}
m2 = {b_["band"]: b_ for b_ in T1["nach_minuten"]}; m2b = {b_["band"]: b_ for b_ in T2["nach_minuten"]}
E = B["test_erwachsene"]; W = {w["delta"]: w for w in B["spielerwert"]["stufen"]}; Q = B["fuenftel"]
K_R, K_EF, K_E, K_C, K_F = ("Startelf-Stärke (Spieler-Ratings), Stand Stichtag", "Mannschaftsstärke, Stand Stichtag",
                            "Mannschaftsstärke laufend (Team-Elo)", "Startelf-Stärke + Mannschaftsstärke laufend", "Häufigkeitsregel")


if EN:
    W1 = lambda k: t2[k]; W2 = lambda k: t2b[k]
    P.zusammenfassung(
        kacheln([("3 ×", f"as likely to break through as the average: the top-rated 2% ({t2['Top 2 %']['treffer']} of {t2['Top 2 %']['n']} versus {pct(T1['basisquote'], 0)})"),
                 (f"{T1['topn'][0]['profi']} of 10", "top-rated youth players are in a professional squad two years later"),
                 (f"+{de(W[0.1]['punkte_30'], 1)} points", "per season from one player who improves the line-up by 0.10 goals per match. Three such players: about 5 points"),
                 (de(N_SPIELER), "players from every league below the professional level, without event data and without data licence costs")]) +
        f"<p><strong>The value in one sentence.</strong> The dashboard shows a club which players below the professional leagues are worth a "
        f"close look, before others discover them and before they become expensive.</p>"
        f"<p><strong>Why this makes money.</strong> (1) <em>Buy cheaper:</em> players from the third to fifth tier and from academies outside "
        f"the big names cost little or nothing. A club that spots them early pays less and gains on resale. (2) <em>More points:</em> a "
        f"stronger line-up wins measurably more often, {pct(Q[4]['heim'])} instead of {pct(Q[0]['heim'])} of matches. Points decide promotion, "
        f"survival and prize money. (3) <em>Scouting time where it pays:</em> instead of screening {de(N_SPIELER)} players, the scout starts from "
        f"a list with three times the hit rate. (4) <em>No data costs:</em> the basis is public match reports. Event data does not exist for "
        f"these leagues anyway.</p>"
        f"<p><strong>Why it can be trusted.</strong> Both claims were tested without looking into the future: ratings were frozen at a cut-off "
        f"date and compared with what happened afterwards, on {de(B['tore']['n'])} later matches and on {de(T1['n'] + T2['n'])} youth players "
        f"in two time windows. A player's value is the difference he makes to his team's goal difference, adjusted for teammates and "
        f"opponents. The method does not replace the scout or the video. It tells you where both are worth it.</p>")

    P.abschnitt("nutzen", "The value for the club", f"""<style>.kern{{break-inside:avoid}}</style>
    <p>This chapter summarises what a club gains from the dashboard. Method and evidence follow from section 3.</p>
    {P.tabelle("Four levers and their evidence. “Measured” means tested in this study on later data. “Mechanism” means it follows from what was measured but is not quantified in euros.",
     ["Lever", "What the club gains", "Evidence", "Type"], [
     ["Find earlier", "Identify talent before it appears in a professional league and becomes expensive",
      f"Top 2%: {t2['Top 2 %']['treffer']} of {t2['Top 2 %']['n']} broke through, average {pct(T1['basisquote'], 0)}. {T1['topn'][0]['profi']} of the top 10 are professionals today.", "measured"],
     ["More points", "Strengthen the line-up deliberately and estimate the effect in points",
      f"+0.10 goals per match = +{de(W[0.1]['punkte_30'], 1)} points per season. Clearly stronger line-up: {pct(Q[4]['heim'])} home wins instead of {pct(Q[0]['heim'])}.", "measured"],
     ["Save scouting time", "Scouts travel to where the hit rate is high",
      f"Shortlist from {de(N_SPIELER)} players in minutes, eight ready-made search profiles", "mechanism"],
     ["No data costs", "Coverage of all leagues below the professional level without an event-data licence",
      f"{de(N_SPIELE)} matches from {D['bewerbe']} competitions, from public match reports only", "measured"]], "llll", breit=True)}
    {P.figur(f"The key evidence in one picture. Of the ten top-rated youth players, {T1['topn'][0]['treffer']} broke through within two years, "
             f"{T1['topn'][0]['profi']} of them into professional football. The average of all players is about {pct(T1['basisquote'], 0)} (dashed).", fig_topn())}
    <p><strong>Who the dashboard is for.</strong> Sporting directors and squad planners who recruit below the professional leagues. Academy
    directors who want to know who is developing outside their own academy. And scouts planning their trips.</p>
    {P.kernaussage("Key takeaways", ["Three times the hit rate at the top, shown in two time windows.",
                                     f"Player values translate into points: +0.10 goals per match is about {de(W[0.1]['punkte_30'], 1)} points per season.",
                                     "Every league below the professional level, without event data."])}
    """)

    P.abschnitt("problem", "Starting point and objective", f"""
    <p>Anyone assessing players from the Regionalliga (third tier), a Landesliga (fourth tier) or an academy faces a gap. The professional
    leagues have event data on every pass and betting odds on every match. Below them, neither exists. Scouting there relies on live
    observation, on goals and on recommendations. That is expensive, patchy and favours strikers, because only goals are counted.</p>
    <p><strong>The objective</strong> of the dashboard is a reliable shortlist: from thousands of players, find those worth a close look.
    For that, the rating must do three things. It must be available for <em>every</em> league, it must capture defenders and midfielders
    as well as goal scorers, and it must demonstrably say something about the future.</p>
    {P.figur("Structure. From three items in the match report the model computes player values and team strengths. The dashboard makes "
             "them accessible in four areas. Three kinds of decisions follow.", fig_aufbau())}
    {P.tabelle("The three questions of this paper.", ["No.", "Question", "Answered in section"], [
     ["1", "What can the dashboard do, and how is it built?", "3"],
     ["2", "How are player value, team strength, win probability and points connected?", "4 and 5"],
     ["3", "Are the ratings right? Do they predict results and later careers?", "6 and 7"]], "lll")}
    {P.kernaussage("Key takeaways", ["Below the professional leagues there is no event data and no betting odds, but there is a match report for every match.",
                                     "The dashboard delivers a shortlist, not a finished decision."])}
    """)

    P.abschnitt("dashboard", "What the dashboard can do", f"""
    <p>The dashboard is a web application in English and German. It loads in under a second and needs no installation. It covers
    {de(N_SPIELER)} players, {de(N_RATING)} of them rated, from the Regionalliga divisions, the top league of each of the nine federal
    states, three Styrian Oberliga divisions and the academy and youth leagues from U15 to U18.</p>
    {P.tabelle("The areas of the dashboard.", ["Area", "What you see", "What for"], [
     ["Scouting", "Ranking of all players with filters for age, league, playing time, position and rating. Eight ready-made search profiles, "
                  "for example “Top talents up to 18”, “Hidden talents outside the academies” or “Standout this season”.", "Shortlist in minutes instead of days"],
     ["Player profile", "A verdict in one sentence and three questions: How good is he now? How good can he become? How reliable is this? "
                        "Plus his impact going forward and defending, his team's record with him on the pitch, and similarly rated players.", "Assessment without statistical training"],
     ["Teams and statistics", "Squad per team and season, average age weighted by minutes, share of minutes for players aged 21 or younger, "
                              "squad chart of playing time against talent rank.", "Which clubs trust young players, who is not getting a chance"],
     ["Matches", "All matches with line-ups, substitutions and events.", "Checking individual appearances"],
     ["Method", "The calculation steps in seven pictures.", "Transparency"]], "lll", breit=True)}
    {P.figur(f"Data volume per season. {de(N_SPIELE)} matches in total; the current season is updated after every round.", fig_daten())}
    <p><strong>The metrics in plain words.</strong> Every number in the dashboard answers a question a sporting director asks anyway.</p>
    {P.tabelle("Metrics and what they mean.", ["Metric", "Question behind it", "How to read it"], [
     ["Overall value", "Does he make his team better?", "Goals of goal difference per 90 minutes compared with an average player. +0.15 means about +4.5 goals over 30 matches."],
     ["Offensive and defensive", "Where does he make a difference?", "Does the team score more with him, does it concede less with him? All team goals count, not just his own."],
     ["Recent-form value", "How is his form?", "The same calculation with recent matches weighted more. One season back counts half."],
     ["Peak value", "How good can he become?", "Today's value projected to the best footballing age around 26."],
     ["Talent rank", "Where does he stand in his birth year?", "Position within the birth year from peak value and playing time, for example “rank 12 of 990”."],
     ["Reliability", "How certain is this?", "Traffic light based on minutes played: reliable, solid or preliminary."]], "lll", breit=True)}
    {P.kernaussage("Key takeaways", ["Four areas: scouting, player profile, teams and statistics, matches.",
                                     "Every metric is translated into a question and a sentence; the raw numbers remain one click away."])}
    """)

    P.abschnitt("methode", "How results turn into player values", f"""
    <p>The method is called plus-minus and comes from basketball and ice hockey. Hvattum (2020) and Hvattum, Kriegl and Čulík (2023)
    developed it for football. The idea is simple: you do not observe what a player does on the ball, but what happens to the score
    while he is on the pitch.</p>
    {P.figur("A match is split at every substitution and every red card. Within each segment the same 22 players are on the pitch, and "
             "the number of goals is known. Across thousands of matches with changing line-ups, the share of each individual can be separated out.", fig_segmente())}
    <p><strong>Step 1: Build segments.</strong> Every match is split at every substitution. {de(N_SPIELE)} matches yield several tens of
    thousands of segments with a fixed line-up.</p>
    <p><strong>Step 2: Rate everyone at once.</strong> One calculation looks for the values of all players simultaneously that best explain
    the goals scored. Because all 22 players of a segment are in the model together, nobody is rewarded for playing in a strong team and
    nobody is punished for playing in a weak one. Home advantage and numerical advantage are separate terms.</p>
    <p><strong>Step 3: Caution with little data.</strong> A player with few minutes stays close to average. Only many minutes allow a value
    that moves clearly away from it. This prevents flukes after three good matches.</p>
    <p><strong>Step 4: Account for age.</strong> Players improve until about 26. The peak value projects today's value to that age, so that
    a 17-year-old can be compared with a 27-year-old. The talent rank then orders players within their birth year.</p>
    {P.kernaussage("Key takeaways", ["What is rated is the impact on the result, not the action on the ball.",
                                     "Teammates, opponents, home advantage and numerical advantage are removed.",
                                     "Little playing time leads to a cautious value close to average."])}
    """)

    P.abschnitt("konnex", "From player values to win probability", f"""
    <p>In professional football, betting odds are the best available estimate of how likely a team is to win. They pool the knowledge of
    many market participants. Odds give the win probability, and the win probability gives the expected points. To assess a team, one
    therefore asks: is it above or below what the market expected?</p>
    <p>Below the professional leagues this market does not exist. The dashboard arrives at the same quantity the other way round. It
    starts with the players and builds the team from them.</p>
    {P.figur("Two routes to the same quantity. In professional football the betting market provides the win probability top-down. Where "
             "there is no market, it is built bottom-up from player values. The second route has an added benefit: it shows which players make up the strength.", fig_kette())}
    <p><strong>The chain in four links.</strong></p>
    <ol>
    <li><strong>Player value.</strong> Every player has a value in goals per 90 minutes.</li>
    <li><strong>Line-up strength.</strong> The sum of the eleven values is the strength of the line-up. The model is built so that this
    sum is directly an expected goal difference.</li>
    <li><strong>Win probability.</strong> The difference between two line-ups gives the probabilities of win, draw and loss.</li>
    <li><strong>Points.</strong> Three points times the win probability plus one point times the draw probability gives the expected points.</li>
    </ol>
    <p><strong>What follows.</strong> A team raises its win probability by fielding players with higher values. The reverse also holds:
    teams that win more than expected have players on the pitch who contribute more than they were given credit for. The model assigns
    this surplus to the players who were on the pitch when it arose. A player in whose appearances the team's goal difference is
    regularly better than expected with those teammates and against those opponents receives a high value. These are exactly the players
    a scout is looking for.</p>
    <p><strong>Team strength and player value are two views.</strong> A pure team strength from results, as measured by an Elo rating,
    answers “How strong is this team?”. It cannot say who is responsible. The player value answers exactly that. Section 6 tests whether
    both views lead to the same result.</p>
    {P.kernaussage("Key takeaways", ["Betting odds give the win probability top-down; player values give it bottom-up.",
                                     "The sum of the eleven player values is an expected goal difference and therefore a win probability.",
                                     "Only the route via the players shows who makes up a team's strength."])}
    """)

    P.abschnitt("prognose", "Evidence 1: Line-up strength predicts results", f"""
    <p><strong>Test design.</strong> Player values were computed only from matches up to June 2025, that is from two seasons. Then they
    were frozen. The test used {de(B['tore']['n'])} later matches from the seasons 2025/26 and 2026/27 that the model had never seen. For
    each match only the starting eleven was used, as known before kick-off. On average {pct(B['bekannt'])} of the starters already had a
    value; all others counted as average players.</p>
    {P.figur(f"Results by line-up strength. The {de(B['tore']['n'])} matches are split into five groups of equal size. When the home line-up "
             f"is clearly stronger by the old player values, it wins {pct(Q[4]['heim'])} of matches and takes {de(Q[4]['ppg'], 2)} points per match. "
             f"When it is clearly weaker, the figures are {pct(Q[0]['heim'])} and {de(Q[0]['ppg'], 2)} points.", fig_fuenftel())}
    <p><strong>The values are right in size as well.</strong> The model claims: one goal of difference in the line-up totals means one goal
    of difference in the result. Measured: {de(B['tore']['steigung'], 2)} goals (uncertainty ± {de(2 * B['tore']['se'], 2)}). The player
    values can therefore be read in real goals and are cautious rather than exaggerated.</p>
    <p><strong>Comparison with pure team strength.</strong> The benchmark is a team strength that learns from results only (Elo). Compared
    is the forecast error for win, draw and loss on the matches of season 2026/27. The conversion into probabilities was calibrated on
    season 2025/26.</p>
    {P.figur("Forecast error compared, smaller is better. In senior football, player values and team strength are equally good at the same "
             "state of knowledge. A continuously updated team strength is better because it knows the results of the current season. In youth "
             "football, team strength carries much more, because academies stay similarly strong over years while squads change every year.", fig_rps())}
    {P.tabelle("Forecast error (ranked probability score) in senior football, season 2026/27.", ["Forecast from", "State of knowledge", "Error", "Correct calls"], [
     ["simple rule, always the same odds", "season 2025/26", de(E[K_F]["rps"], 4), pct(E[K_F]["treffer"], 1)],
     ["player values of the line-up", "up to June 2025", de(E[K_R]["rps"], 4), pct(E[K_R]["treffer"], 1)],
     ["team strength", "up to June 2025", de(E[K_EF]["rps"], 4), pct(E[K_EF]["treffer"], 1)],
     ["team strength", "up to the previous day", de(E[K_E]["rps"], 4), pct(E[K_E]["treffer"], 1)],
     ["player values and team strength", "mixed", de(E[K_C]["rps"], 4), pct(E[K_C]["treffer"], 1)]], "llrr")}
    <p><strong>How to read this.</strong> Player values are not a betting model. For forecasting the next match, a continuously updated
    team strength is superior, as one would expect. The decisive point is a different one: values that are more than a year old and cover
    only two thirds of the starters explain results as well as the team strength of the same date. A large part of a team's strength
    therefore sits in the individual values of its players, and only these can be transferred to another club.</p>
    {P.figur(f"What a better player is worth in points. Based on {de(B['spielerwert']['n'])} matches in senior football. A player who improves "
             f"the line-up by 0.10 goals per match brings about {de(W[0.1]['punkte_30'], 1)} points in 30 matches. Three such players correspond "
             "to about five points. pp = percentage points.", fig_spielerwert())}
    {P.kernaussage("Key takeaways", [f"Clearly stronger line-up: {pct(Q[4]['heim'])} home wins. Clearly weaker: {pct(Q[0]['heim'])}.",
                                     f"One goal of difference in player values corresponds to a measured {de(B['tore']['steigung'], 2)} goals in the result.",
                                     "At the same state of knowledge, player values are as accurate as team strength and additionally show who carries it.",
                                     f"+0.10 goals per match in the line-up is about {de(W[0.1]['punkte_30'], 1)} points per season."])}
    """)

    BN = {"Top 2 %": "top 2%", "Top 5 %": "top 5%", "Top 10 %": "top 10%", "Top 20 %": "top 20%", "20 bis 50 %": "20 to 50%", "untere Hälfte": "bottom half"}
    P.abschnitt("talent", "Evidence 2: The rating identifies future risers early", f"""
    <p><strong>Test design.</strong> A club's question is: when the dashboard shows a youth player at the very top, how often does such a
    player make it? To answer this, the ratings were frozen at an earlier date and compared with what happened afterwards. Two time
    windows were tested.</p>
    {P.tabelle("The two time windows.", ["", "Rating from", "Outcome measured", "Players", "Average breakthrough"], [
     ["Window 1", "season 2023/24", "from season 2025/26", de(T1["n"]), pct(T1["basisquote"], 1)],
     ["Window 2", "seasons 2023/24 and 2024/25", "from season 2026/27", de(T2["n"]), pct(T2["basisquote"], 1)]], "lllrr")}
    <p>Included are youth players with at least 900 minutes in the last season before the cut-off. <strong>Breakthrough</strong> means:
    the player is in the squad of a club in the Bundesliga or 2. Liga today, or he is a regular in a Regionalliga (at least 900 minutes
    in window 1, at least 300 minutes in window 2, because season 2026/27 is only one third played).</p>
    {P.figur("Share of players with a breakthrough by earlier classification. Green: classified by talent rank, with uncertainty range. Grey: "
             "the same calculation when ranking by minutes played only. The dashed line is the average of all players. The talent rank "
             "separates clearly in both windows, most strongly at the top.", fig_talent())}
    {P.tabelle("Hit rates by classification. Reading example: of the top 10% by talent rank, " +
               f"{t2['Top 10 %']['treffer']} of {t2['Top 10 %']['n']} broke through in window 1.", ["Classification", "Window 1", "Window 2", "Window 1, minutes only", "Window 2, minutes only"],
     [[BN[k], f"{pct(t2[k]['quote'], 0)} ({t2[k]['treffer']} of {t2[k]['n']})", f"{pct(t2b[k]['quote'], 0)} ({t2b[k]['treffer']} of {t2b[k]['n']})",
       pct(m2[k]["quote"], 0), pct(m2b[k]["quote"], 0)] for k in ("Top 2 %", "Top 5 %", "Top 10 %", "Top 20 %", "20 bis 50 %", "untere Hälfte")] +
     [["all", pct(T1["basisquote"], 0), pct(T2["basisquote"], 0), pct(T1["basisquote"], 0), pct(T2["basisquote"], 0)]], "lrrrr")}
    <p><strong>What the numbers say.</strong> The top 2% break through about three times as often as the average, the top 10% almost twice
    as often, the bottom half clearly less often. Ranking by minutes played alone finds hardly more than the average at the top. The added
    value therefore comes from the rating, not from playing time alone.</p>
    <p><strong>The check by name</strong> is shown in figure 1: of the ten top-rated players from window 1, {T1['topn'][0]['treffer']} broke
    through; among the top 30 it is {T1['topn'][2]['treffer']}, among the top 50 {T1['topn'][3]['treffer']}.</p>
    <p><strong>Putting the often-quoted 80% in context.</strong> The literature states that the top 20% by this method contain about 80% of
    the later most valuable players. In our data the top 20% contain {pct(t2['Top 20 %']['erfasst'], 0)} (window 1) and
    {pct(t2b['Top 20 %']['erfasst'], 0)} (window 2) of the later risers. There are two reasons for the difference: our sample contains only
    players who already play a lot, and the observation period of two years is short. For practice the hit rate is the more important
    number: it says how often a close look pays off.</p>
    {P.kernaussage("Key takeaways", [f"Top 2%: {t2['Top 2 %']['treffer']} of {t2['Top 2 %']['n']} with a breakthrough (window 1), "
                                     f"{t2b['Top 2 %']['treffer']} of {t2b['Top 2 %']['n']} (window 2). Average: {pct(T1['basisquote'], 0)} and {pct(T2['basisquote'], 0)}.",
                                     f"Of the ten top-rated players, {T1['topn'][0]['profi']} play in a professional league.",
                                     "Minutes played alone do not achieve this. The added value comes from the rating."])}
    """)

    P.abschnitt("vorteil", "Why this works without event data", f"""
    <p>Event data describes what a player does on the ball. It is expensive to collect and therefore available only for the upper
    leagues. The plus-minus method does not need it, because it starts from the result and not from the action.</p>
    {P.figur("Coverage. Event data and betting odds end at the border to professional football. Match reports exist for every match in "
             "every league. The method can be used exactly where most players are still undiscovered.", fig_abdeckung())}
    {P.tabelle("Event data and results data compared.", ["", "Event data", "Results data (this method)"], [
     ["Available for", "professional leagues and a few below", "every league with a match report, including youth"],
     ["Cost per match", "high, collected by people or cameras", "practically zero, match reports are public"],
     ["Measures", "actions on the ball", "impact on the result"],
     ["Strength", "explains how a player plays", "also captures runs, positioning and defensive work that no event records"],
     ["Weakness", "rates what is visible and countable", "needs many matches and does not say why a player has impact"],
     ["Best use", "profile and playing style", "shortlist and ranking"]], "lll", breit=True)}
    <p><strong>The real advantage.</strong> The two kinds of data complement each other. The method does not replace the scout or the
    video. It says <em>for whom</em> both are worth it. In a market of more than {de(round(N_SPIELER, -3))} players that is the bottleneck:
    nobody can watch them all. Section 7 shows that the shortlist roughly triples the hit rate at the top.</p>
    {P.kernaussage("Key takeaways", ["Results data exists for every league, event data only for the upper ones.",
                                     "The method also captures impact that no event records, such as defensive work.",
                                     "It does not replace scout and video, but says where both pay off."])}
    """)

    def fig_unsicher():
        fig, ax = plt.subplots(figsize=(7.4, 2.2)); bb = T1["nach_talent"][:4]
        for i, b_ in enumerate(bb):
            ax.plot([b_["ci"][0], b_["ci"][1]], [i, i], color=GREEN, lw=5, solid_capstyle="round", alpha=.35); ax.plot([b_["quote"]], [i], "o", color=GREEN, ms=7)
            ax.text(b_["ci"][1] + 1.5, i, f"{b_['treffer']} of {b_['n']}", va="center", fontsize=8)
        ax.axvline(T1["basisquote"], color=CB, lw=1.1, ls=(0, (4, 3))); ax.set_yticks(range(4)); ax.set_yticklabels([BN[b_["band"]] for b_ in bb]); ax.invert_yaxis()
        ax.set_xlim(0, 105); ax.set_xlabel("share with breakthrough in %, dot = measured, bar = uncertainty range")
        return svg(fig)

    P.abschnitt("grenzen", "Limitations", f"""
    <p>The results are robust enough for a shortlist. On their own they are not sufficient for a transfer decision. The main limitations:</p>
    <ol>
    <li><strong>Short period.</strong> The data starts in 2023/24. The longest possible look back covers two years. Whether a player stays in
    professional football cannot yet be measured.</li>
    <li><strong>Small numbers at the top.</strong> The top 2% are eleven to twelve players per window. The figures show the uncertainty
    range. The direction is the same in both windows, the exact level is not.</li>
    <li><strong>Breakthrough is only partly visible.</strong> Professional leagues and foreign leagues are not part of the match data.
    Professional status comes from the association's public player profiles and may be out of date. Players who moved abroad count as no
    breakthrough. The true rates are more likely higher. A comparison with a database on professional football is prepared.</li>
    <li><strong>Academy effect.</strong> Players from large academies have better chances regardless of their rating. Part of the hit rate
    is due to this. The comparison within the same academy is still outstanding.</li>
    <li><strong>Second teams.</strong> A regular place in the second team of a professional club in the Regionalliga counts as a
    breakthrough here. It can also be seen as a preliminary stage.</li>
    <li><strong>Little playing time.</strong> Below about 900 minutes a value is preliminary. The dashboard shows this as a traffic light.</li>
    <li><strong>No substitute for team strength.</strong> For forecasting the next match, a continuously updated team strength is better.
    Player values answer a different question.</li>
    </ol>
    {P.figur("Uncertainty at the top, window 1. The smaller the group, the wider the range in which the true hit rate lies. Even the lower "
             "bound of the top 2% is above the average of all players.", fig_unsicher())}
    {P.kernaussage("Key takeaways", ["Two years of look back, small groups at the top: direction established, level with uncertainty.",
                                     "Moves abroad and into professional leagues are recorded incompletely; the true rates are more likely higher."])}
    """)

    P.literatur({
     "Method: plus-minus and talent": [
      ("Hvattum, L. M. (2019).", "A comprehensive review of plus-minus ratings for evaluating individual players in team sports. <i>International Journal of Computer Science in Sport</i> 18(1), 1–23.", "overview"),
      ("Hvattum, L. M. (2020).", "Offensive and defensive plus-minus player ratings for soccer. <i>Applied Sciences</i> 10(20), 7345.", "section 4"),
      ("Hvattum, L. M., Kriegl, M.-A. and Čulík, M. (2023).", "Identifying talent with plus-minus ratings in association football. In Y. Dominicy and C. Ley (eds.), <i>Statistics Meets Sports</i>, 175–200. Cambridge Scholars.", "peak value, talent rank, section 7"),
      ("Kharrat, T., McHale, I. G. and López Peña, J. (2020).", "Plus-minus player ratings for soccer. <i>European Journal of Operational Research</i> 283(2), 726–736.", "player value in points"),
      ("Arntzen, H. and Hvattum, L. M. (2021).", "Predicting match outcomes in association football using team ratings and player ratings. <i>Statistical Modelling</i> 21(5), 449–470.", "section 6")],
     "Team strength, betting odds, forecast quality": [
      ("Hvattum, L. M. and Arntzen, H. (2010).", "Using ELO ratings for match result prediction in association football. <i>International Journal of Forecasting</i> 26(3), 460–470.", "team strength"),
      ("Štrumbelj, E. (2014).", "On determining probability forecasts from betting odds. <i>International Journal of Forecasting</i> 30(4), 934–943.", "odds and probability"),
      ("Wunderlich, F. and Memmert, D. (2018).", "The betting odds rating system: Using soccer forecasts to forecast soccer. <i>PLOS ONE</i> 13(6), e0198668.", "odds as benchmark"),
      ("Epstein, E. S. (1969).", "A scoring system for probability forecasts of ranked categories. <i>Journal of Applied Meteorology</i> 8, 985–987.", "forecast error"),
      ("Constantinou, A. C. and Fenton, N. E. (2012).", "Solving the problem of inadequate scoring rules for assessing probabilistic football forecast models. <i>Journal of Quantitative Analysis in Sports</i> 8(1).", "forecast error")],
     "Public sources": [
      ("Austrian Football Association (ÖFB).", "Public match reports and player profiles of the competitions from season 2023/24, oefb.at.", "results, line-ups, goal minutes")]})

else:
    P.zusammenfassung(
        kacheln([("3 ×", f"so oft schaffen die bestbewerteten 2 % den Durchbruch wie der Durchschnitt ({t2['Top 2 %']['treffer']} von {t2['Top 2 %']['n']} gegenüber {pct(T1['basisquote'], 0)})"),
                 (f"{T1['topn'][0]['profi']} von 10", "der bestbewerteten Nachwuchsspieler stehen zwei Jahre später im Kader eines Profiklubs"),
                 (f"+{de(W[0.1]['punkte_30'], 1)} Punkte", "je Saison bringt ein Spieler, der die Startelf um 0,10 Tore je Spiel verbessert. Drei solche Spieler: rund 5 Punkte"),
                 (de(N_SPIELER), "Spieler aus allen Ligen unterhalb der Profis, ohne Eventdaten und ohne Lizenzkosten für Daten")]) +
        f"<p><strong>Der Nutzen in einem Satz.</strong> Das Dashboard zeigt einem Klub, bei welchen Spielern unterhalb der Profiligen sich das "
        f"genaue Hinsehen lohnt, bevor andere sie entdecken und bevor sie teuer werden.</p>"
        f"<p><strong>Warum das Geld bringt.</strong> (1) <em>Günstiger einkaufen:</em> Spieler aus Regionalliga, Landesliga und Akademien außerhalb "
        f"der großen Namen kosten wenig oder nichts. Wer sie früh erkennt, zahlt weniger und gewinnt beim Weiterverkauf. (2) <em>Mehr Punkte:</em> "
        f"Eine stärker besetzte Startelf gewinnt messbar öfter, {pct(Q[4]['heim'])} statt {pct(Q[0]['heim'])} der Spiele. Punkte entscheiden über "
        f"Aufstieg, Klassenerhalt und Prämien. (3) <em>Scouting-Zeit gezielt einsetzen:</em> Statt {de(N_SPIELER)} Spieler zu sichten, beginnt der "
        f"Scout bei einer Liste, deren Trefferquote dreimal so hoch ist. (4) <em>Keine Datenkosten:</em> Grundlage sind öffentliche Spielberichte, "
        f"Eventdaten gibt es für diese Ligen ohnehin nicht.</p>"
        f"<p><strong>Warum man dem trauen kann.</strong> Beide Aussagen sind ohne Blick in die Zukunft geprüft: Die Bewertungen wurden zu einem "
        f"Stichtag eingefroren und mit dem verglichen, was danach geschah, an {de(B['tore']['n'])} späteren Spielen und an {de(T1['n'] + T2['n'])} "
        f"Nachwuchsspielern in zwei Zeitfenstern. Der Wert eines Spielers ist dabei der Unterschied, den er für die Tordifferenz seiner Mannschaft "
        f"macht, bereinigt um Mitspieler und Gegner. Das Verfahren ersetzt nicht den Scout und nicht das Video. Es sagt, wo beides lohnt.</p>")

    P.abschnitt("nutzen", "Der Nutzen für den Klub", f"""<style>.kern{{break-inside:avoid}}</style>
    <p>Dieses Kapitel fasst zusammen, was ein Klub von dem Dashboard hat. Die Methode und die Nachweise folgen ab Abschnitt 3.</p>
    {P.tabelle("Vier Hebel und ihr Beleg. „Gemessen“ heißt: in dieser Studie an späteren Daten geprüft. „Mechanismus“ heißt: folgt aus dem Gemessenen, ist aber nicht in Euro beziffert.",
     ["Hebel", "Was der Klub davon hat", "Beleg", "Art"], [
     ["Früher finden", "Talente erkennen, bevor sie in einer Profiliga auftauchen und teuer werden",
      f"Beste 2 %: {t2['Top 2 %']['treffer']} von {t2['Top 2 %']['n']} mit Durchbruch, Durchschnitt {pct(T1['basisquote'], 0)}. {T1['topn'][0]['profi']} der besten 10 heute Profis.", "gemessen"],
     ["Mehr Punkte", "Die Startelf gezielt verstärken und den Effekt in Punkten abschätzen",
      f"+0,10 Tore je Spiel = +{de(W[0.1]['punkte_30'], 1)} Punkte je Saison. Klar stärkere Elf: {pct(Q[4]['heim'])} Heimsiege statt {pct(Q[0]['heim'])}.", "gemessen"],
     ["Scouting-Zeit sparen", "Scouts fahren dorthin, wo die Trefferquote hoch ist",
      f"Vorauswahl aus {de(N_SPIELER)} Spielern in Minuten, acht fertige Suchprofile", "Mechanismus"],
     ["Keine Datenkosten", "Abdeckung aller Ligen unterhalb der Profis ohne Lizenz für Eventdaten",
      f"{de(N_SPIELE)} Spiele aus {D['bewerbe']} Bewerben, nur aus öffentlichen Spielberichten", "gemessen"]], "llll", breit=True)}
    {P.figur(f"Der wichtigste Beleg in einem Bild. Von den zehn bestbewerteten Nachwuchsspielern haben {T1['topn'][0]['treffer']} binnen zwei Jahren den "
             f"Durchbruch geschafft, {T1['topn'][0]['profi']} davon im Profifußball. Im Durchschnitt aller Spieler sind es rund {pct(T1['basisquote'], 0)} (gestrichelt).", fig_topn())}
    <p><strong>Für wen das Dashboard gedacht ist.</strong> Für Sportdirektoren und Kaderplaner, die unterhalb der Profiligen einkaufen. Für
    Akademieleiter, die wissen wollen, wer außerhalb der eigenen Akademie heranwächst. Und für Scouts, die ihre Fahrten planen.</p>
    {P.kernaussage("Kernaussagen", ["Dreimal so hohe Trefferquote an der Spitze, belegt an zwei Zeitfenstern.",
                                    f"Spielerwerte lassen sich in Punkte übersetzen: +0,10 Tore je Spiel sind rund {de(W[0.1]['punkte_30'], 1)} Punkte je Saison.",
                                    "Alle Ligen unterhalb der Profis, ohne Eventdaten."])}
    """)

    P.abschnitt("problem", "Ausgangslage und Ziel", f"""
    <p>Wer Spieler aus der Regionalliga, einer Landesliga oder einer Akademie beurteilen will, steht vor einer Lücke. In den Profiligen
    gibt es Eventdaten zu jedem Pass und Wettquoten zu jedem Spiel. Darunter gibt es beides nicht. Scouting stützt sich dort auf
    Beobachtung vor Ort, auf Tore und auf Empfehlungen. Das ist teuer, lückenhaft und bevorzugt Stürmer, weil nur Tore gezählt werden.</p>
    <p><strong>Ziel</strong> des Dashboards ist eine belastbare Vorauswahl: Aus Tausenden Spielern jene finden, bei denen sich das genaue
    Hinsehen lohnt. Dafür muss die Bewertung drei Dinge leisten. Sie muss für <em>jede</em> Liga verfügbar sein, sie muss Verteidiger und
    Mittelfeldspieler genauso erfassen wie Torschützen, und sie muss nachweislich etwas über die Zukunft sagen.</p>
    {P.figur("Aufbau. Aus drei Angaben des Spielberichts rechnet das Modell Spielerwerte und Mannschaftsstärken. Das Dashboard macht sie "
             "in vier Bereichen zugänglich. Am Ende stehen drei Arten von Entscheidungen.", fig_aufbau())}
    {P.tabelle("Die drei Fragen dieses Papiers.", ["Nr.", "Frage", "Antwort in Abschnitt"], [
     ["1", "Was kann das Dashboard, und wie ist es aufgebaut?", "3"],
     ["2", "Wie hängen Spielerwert, Mannschaftsstärke, Gewinnwahrscheinlichkeit und Punkte zusammen?", "4 und 5"],
     ["3", "Stimmen die Bewertungen? Sagen sie Ergebnisse und spätere Karrieren voraus?", "6 und 7"]], "lll")}
    {P.kernaussage("Kernaussagen", ["Unterhalb der Profiligen fehlen Eventdaten und Wettquoten, Spielberichte gibt es aber für jedes Spiel.",
                                    "Das Dashboard liefert eine Vorauswahl, keine fertige Entscheidung."])}
    """)

    P.abschnitt("dashboard", "Was das Dashboard kann", f"""
    <p>Das Dashboard ist eine Webanwendung in Deutsch und Englisch. Es lädt in unter einer Sekunde und braucht keine Installation.
    Es umfasst {de(N_SPIELER)} Spieler, davon {de(N_RATING)} mit Bewertung, aus den Regionalligen, den höchsten Ligen aller neun
    Bundesländer, drei steirischen Oberligen und den Akademie- und Nachwuchsligen U15 bis U18.</p>
    {P.tabelle("Die Bereiche des Dashboards.", ["Bereich", "Was man sieht", "Wofür"], [
     ["Scouting", "Rangliste aller Spieler mit Filtern nach Alter, Liga, Einsatzzeit, Position und Bewertung. Acht fertige Filter-Vorlagen, "
                  "zum Beispiel „Top-Talente bis 18“, „Hidden Talents außerhalb der Akademien“ oder „Auffällig in dieser Saison“.", "Vorauswahl in Minuten statt Tagen"],
     ["Spielerprofil", "Ein Urteil in einem Satz und drei Fragen: Wie gut ist er jetzt? Wie gut kann er werden? Wie sicher ist das? "
                       "Dazu die Wirkung nach vorne und hinten, die Bilanz seiner Mannschaft mit ihm am Platz und ähnlich bewertete Spieler.", "Einordnung ohne Statistikkenntnis"],
     ["Teams und Statistik", "Kader je Mannschaft und Saison, Durchschnittsalter nach Einsatzzeit, Anteil der Minuten von Spielern bis 21, "
                             "Kader als Diagramm aus Einsatzzeit und Talent-Rang.", "Welche Klubs setzen auf Junge, wer kommt nicht zum Zug"],
     ["Spiele", "Alle Spiele mit Aufstellungen, Wechseln und Ereignissen.", "Nachprüfen einzelner Einsätze"],
     ["Methodik", "Die Rechenschritte in sieben Bildern.", "Nachvollziehbarkeit"]], "lll", breit=True)}
    {P.figur(f"Datenumfang je Saison. Insgesamt {de(N_SPIELE)} Spiele, die laufende Saison wird nach jeder Runde ergänzt.", fig_daten())}
    <p><strong>Die Kennzahlen in einfachen Worten.</strong> Jede Zahl im Dashboard beantwortet eine Frage, die ein Sportdirektor ohnehin stellt.</p>
    {P.tabelle("Kennzahlen und ihre Bedeutung.", ["Kennzahl", "Frage dahinter", "Lesart"], [
     ["Gesamtwert", "Macht er seine Mannschaft besser?", "Tore Tordifferenz je 90 Minuten gegenüber einem Durchschnittsspieler. +0,15 heißt rund +4,5 Tore über 30 Spiele."],
     ["Offensiv und Defensiv", "Wo wirkt er?", "Erzielt die Mannschaft mit ihm mehr Tore, kassiert sie mit ihm weniger? Es zählen alle Tore der Mannschaft, nicht nur seine eigenen."],
     ["Aktueller Wert", "Wie ist seine Form?", "Dieselbe Rechnung, jüngere Spiele zählen mehr. Eine Saison zurück zählt halb."],
     ["Peak-Wert", "Wie gut kann er werden?", "Der heutige Wert, hochgerechnet auf das beste Fußballalter um 26."],
     ["Talent-Rang", "Wo steht er in seinem Jahrgang?", "Platz im Geburtsjahrgang aus Peak-Wert und Einsatzzeit, zum Beispiel „Platz 12 von 990“."],
     ["Verlässlichkeit", "Wie sicher ist das?", "Ampel aus den Einsatzminuten: belastbar, solide oder vorläufig."]], "lll", breit=True)}
    {P.kernaussage("Kernaussagen", ["Vier Bereiche: Scouting, Spielerprofil, Teams und Statistik, Spiele.",
                                    "Jede Kennzahl ist in eine Frage und einen Satz übersetzt, die Rohzahlen bleiben aufklappbar."])}
    """)

    P.abschnitt("methode", "Wie aus Ergebnissen Spielerwerte werden", f"""
    <p>Die Methode heißt Plus-Minus und stammt aus Basketball und Eishockey. Für den Fußball haben sie Hvattum (2020) und
    Hvattum, Kriegl und Čulík (2023) ausgearbeitet. Der Gedanke ist einfach: Man beobachtet nicht, was ein Spieler am Ball tut, sondern
    was mit dem Ergebnis passiert, während er am Platz steht.</p>
    {P.figur("Ein Spiel wird an jedem Wechsel und jeder Roten Karte geteilt. In jedem Abschnitt stehen dieselben 22 Spieler am Platz, und "
             "man weiß, wie viele Tore gefallen sind. Über Tausende Spiele mit wechselnden Aufstellungen lässt sich der Anteil jedes "
             "Einzelnen herausrechnen.", fig_segmente())}
    <p><strong>Schritt 1: Abschnitte bilden.</strong> Jedes Spiel wird an jeder Ein- und Auswechslung geteilt. Aus {de(N_SPIELE)} Spielen
    entstehen so mehrere Zehntausend Abschnitte mit fester Besetzung.</p>
    <p><strong>Schritt 2: Alle gleichzeitig bewerten.</strong> Eine Rechnung sucht für alle Spieler zugleich jene Werte, die die gefallenen
    Tore am besten erklären. Weil alle 22 Spieler eines Abschnitts gemeinsam im Modell stehen, wird niemand dafür belohnt, in einer
    starken Mannschaft zu spielen, und niemand dafür bestraft, in einer schwachen zu stehen. Heimvorteil und Überzahl sind eigene Größen.</p>
    <p><strong>Schritt 3: Vorsicht bei wenig Daten.</strong> Wer wenig gespielt hat, bleibt nahe am Durchschnitt. Erst viele Minuten
    erlauben einen Wert, der sich deutlich davon entfernt. Das verhindert Zufallstreffer nach drei guten Spielen.</p>
    <p><strong>Schritt 4: Alter berücksichtigen.</strong> Spieler werden bis etwa 26 besser. Der Peak-Wert rechnet den heutigen Wert auf
    dieses Alter hoch, damit ein 17-Jähriger mit einem 27-Jährigen vergleichbar wird. Der Talent-Rang ordnet danach innerhalb des
    Geburtsjahrgangs.</p>
    {P.kernaussage("Kernaussagen", ["Bewertet wird die Wirkung auf das Ergebnis, nicht die Aktion am Ball.",
                                    "Mitspieler, Gegner, Heimvorteil und Überzahl sind herausgerechnet.",
                                    "Wenig Einsatzzeit führt zu einem vorsichtigen Wert nahe am Durchschnitt."])}
    """)

    P.abschnitt("konnex", "Von Spielerwerten zur Gewinnwahrscheinlichkeit", f"""
    <p>Im Profifußball ist die Wettquote die beste verfügbare Schätzung dafür, wie wahrscheinlich eine Mannschaft gewinnt. Sie bündelt
    das Wissen vieler Marktteilnehmer. Aus der Quote folgt die Gewinnwahrscheinlichkeit, daraus die erwarteten Punkte. Wer eine Mannschaft
    bewerten will, fragt deshalb: Liegt sie über oder unter dem, was der Markt erwartet hat?</p>
    <p>Unterhalb der Profiligen gibt es diesen Markt nicht. Das Dashboard kommt zur selben Größe auf dem umgekehrten Weg. Es beginnt bei
    den Spielern und baut die Mannschaft daraus auf.</p>
    {P.figur("Zwei Wege zur selben Größe. Im Profifußball liefert der Wettmarkt die Gewinnwahrscheinlichkeit von oben. Wo es keinen Markt "
             "gibt, entsteht sie von unten aus den Spielerwerten. Der zweite Weg hat einen Zusatznutzen: Er zeigt, welche Spieler die "
             "Stärke ausmachen.", fig_kette())}
    <p><strong>Die Kette in vier Gliedern.</strong></p>
    <ol>
    <li><strong>Spielerwert.</strong> Jeder Spieler hat einen Wert in Toren je 90 Minuten.</li>
    <li><strong>Startelf-Stärke.</strong> Die Summe der elf Werte ist die Stärke der Aufstellung. Das Modell ist so gebaut, dass diese
    Summe direkt eine erwartete Tordifferenz ergibt.</li>
    <li><strong>Gewinnwahrscheinlichkeit.</strong> Aus dem Unterschied zweier Startelfs folgen die Wahrscheinlichkeiten für Sieg, Remis und
    Niederlage.</li>
    <li><strong>Punkte.</strong> Drei Punkte mal Siegwahrscheinlichkeit plus ein Punkt mal Remiswahrscheinlichkeit ergibt die erwarteten Punkte.</li>
    </ol>
    <p><strong>Was daraus folgt.</strong> Eine Mannschaft erhöht ihre Gewinnwahrscheinlichkeit, wenn sie Spieler mit höherem Wert aufstellt.
    Umgekehrt gilt: Mannschaften, die mehr gewinnen als erwartet, haben Spieler am Platz, die mehr beitragen, als man ihnen zugetraut hat.
    Das Modell ordnet diesen Überschuss den Spielern zu, die am Platz standen, als er entstand. Ein Spieler, bei dessen Einsätzen die
    Tordifferenz seiner Mannschaft regelmäßig besser ausfällt als mit den übrigen Mitspielern und gegen dieselben Gegner zu erwarten war,
    bekommt einen hohen Wert. Genau diese Spieler sucht ein Scout.</p>
    <p><strong>Mannschaftsstärke und Spielerwert sind zwei Sichten.</strong> Eine reine Mannschaftsstärke aus Ergebnissen, wie sie ein
    Elo-Wert misst, beantwortet „Wie stark ist dieses Team?“. Sie kann nicht sagen, wer dafür verantwortlich ist. Der Spielerwert
    beantwortet genau das. Abschnitt 6 prüft, ob beide Sichten zum selben Ergebnis kommen.</p>
    {P.kernaussage("Kernaussagen", ["Wettquoten liefern die Gewinnwahrscheinlichkeit von oben, Spielerwerte liefern sie von unten.",
                                    "Die Summe der elf Spielerwerte ist eine erwartete Tordifferenz und damit eine Gewinnwahrscheinlichkeit.",
                                    "Nur der Weg über die Spieler zeigt, wer die Stärke einer Mannschaft ausmacht."])}
    """)

    P.abschnitt("prognose", "Nachweis 1: Die Startelf-Stärke sagt Ergebnisse voraus", f"""
    <p><strong>Aufbau der Prüfung.</strong> Die Spielerwerte wurden nur aus Spielen bis Juni 2025 gerechnet, also aus zwei Saisonen. Danach
    wurden sie eingefroren. Geprüft wurde an {de(B['tore']['n'])} späteren Spielen der Saisonen 2025/26 und 2026/27, die das Modell nie
    gesehen hat. Für jedes Spiel wurde nur die Startelf verwendet, wie sie vor dem Anpfiff bekannt ist. Im Schnitt hatten
    {pct(B['bekannt'])} der Starter bereits einen Wert, alle anderen zählten als Durchschnittsspieler.</p>
    {P.figur(f"Ergebnisse nach Stärke der Startelf. Die {de(B['tore']['n'])} Spiele sind in fünf gleich große Gruppen geteilt. Ist die Heimelf "
             f"nach den alten Spielerwerten klar stärker, gewinnt sie {pct(Q[4]['heim'])} der Spiele und holt {de(Q[4]['ppg'], 2)} Punkte je Spiel. "
             f"Ist sie klar schwächer, sind es {pct(Q[0]['heim'])} und {de(Q[0]['ppg'], 2)} Punkte.", fig_fuenftel())}
    <p><strong>Die Werte stimmen auch in der Höhe.</strong> Das Modell behauptet: Ein Tor Unterschied in der Startelf-Summe bedeutet ein Tor
    Unterschied im Ergebnis. Gemessen wurden {de(B['tore']['steigung'], 2)} Tore (Unsicherheit ± {de(2 * B['tore']['se'], 2)}). Die Spielerwerte sind
    also in echten Toren zu lesen und eher vorsichtig als übertrieben.</p>
    <p><strong>Vergleich mit der reinen Mannschaftsstärke.</strong> Als Messlatte dient eine Mannschaftsstärke, die nur aus Ergebnissen
    lernt (Elo). Verglichen wird der Prognosefehler für Sieg, Remis und Niederlage an den Spielen der Saison 2026/27. Die Umrechnung in
    Wahrscheinlichkeiten wurde an der Saison 2025/26 eingestellt.</p>
    {P.figur("Prognosefehler im Vergleich, kleiner ist besser. Im Erwachsenenfußball sind Spielerwerte und Mannschaftsstärke bei gleichem "
             "Wissensstand gleich gut. Eine laufend aktualisierte Mannschaftsstärke ist besser, weil sie die Ergebnisse der laufenden Saison "
             "kennt. Im Nachwuchs trägt die Mannschaftsstärke deutlich mehr, weil Akademien über Jahre ähnlich stark bleiben, die Kader aber "
             "jedes Jahr wechseln.", fig_rps())}
    {P.tabelle("Prognosefehler (Ranked Probability Score) im Erwachsenenfußball, Saison 2026/27.", ["Prognose aus", "Wissensstand", "Fehler", "richtig getippt"], [
     ["einfache Regel, immer dieselbe Quote", "Saison 2025/26", de(E[K_F]["rps"], 4), pct(E[K_F]["treffer"], 1)],
     ["Spielerwerte der Startelf", "bis Juni 2025", de(E[K_R]["rps"], 4), pct(E[K_R]["treffer"], 1)],
     ["Mannschaftsstärke", "bis Juni 2025", de(E[K_EF]["rps"], 4), pct(E[K_EF]["treffer"], 1)],
     ["Mannschaftsstärke", "bis zum Vortag", de(E[K_E]["rps"], 4), pct(E[K_E]["treffer"], 1)],
     ["Spielerwerte und Mannschaftsstärke", "gemischt", de(E[K_C]["rps"], 4), pct(E[K_C]["treffer"], 1)]], "llrr")}
    <p><strong>Lesart.</strong> Die Spielerwerte sind kein Wettmodell. Für die Prognose des nächsten Spiels ist eine laufend aktualisierte
    Mannschaftsstärke überlegen, und das ist zu erwarten. Entscheidend ist etwas anderes: Werte, die über ein Jahr alt sind und nur zwei
    Drittel der Starter abdecken, erklären Ergebnisse so gut wie die Mannschaftsstärke desselben Stands. Die Stärke einer Mannschaft steckt
    also zu einem großen Teil in den Einzelwerten ihrer Spieler, und nur diese lassen sich auf einen anderen Klub übertragen.</p>
    {P.figur(f"Was ein besserer Spieler in Punkten wert ist. Grundlage sind {de(B['spielerwert']['n'])} Spiele im Erwachsenenfußball. "
             f"Ein Spieler, der die Startelf um 0,10 Tore je Spiel verbessert, bringt rund {de(W[0.1]['punkte_30'], 1)} Punkte in 30 Spielen. "
             "Drei solche Spieler entsprechen etwa fünf Punkten. PP = Prozentpunkte.", fig_spielerwert())}
    {P.kernaussage("Kernaussagen", [f"Klar stärkere Startelf: {pct(Q[4]['heim'])} Heimsiege. Klar schwächere: {pct(Q[0]['heim'])}.",
                                    f"Ein Tor Unterschied in den Spielerwerten entspricht gemessen {de(B['tore']['steigung'], 2)} Toren im Ergebnis.",
                                    "Bei gleichem Wissensstand sind Spielerwerte so treffsicher wie eine Mannschaftsstärke, zeigen aber zusätzlich, wer sie trägt.",
                                    f"+0,10 Tore je Spiel in der Startelf sind rund {de(W[0.1]['punkte_30'], 1)} Punkte je Saison."])}
    """)

    P.abschnitt("talent", "Nachweis 2: Das Rating erkennt spätere Aufsteiger früh", f"""
    <p><strong>Aufbau der Prüfung.</strong> Die Frage eines Klubs lautet: Wenn das Dashboard einen Nachwuchsspieler ganz oben zeigt, wie oft
    wird aus so einem Spieler etwas? Dazu wurden die Bewertungen zu einem früheren Zeitpunkt eingefroren und mit dem verglichen, was danach
    geschah. Geprüft wurden zwei Zeitfenster.</p>
    {P.tabelle("Die beiden Zeitfenster.", ["", "Bewertung aus", "Ergebnis gemessen", "Spieler", "Durchbruch im Schnitt"], [
     ["Fenster 1", "Saison 2023/24", "ab Saison 2025/26", de(T1["n"]), pct(T1["basisquote"], 1)],
     ["Fenster 2", "Saisonen 2023/24 und 2024/25", "ab Saison 2026/27", de(T2["n"]), pct(T2["basisquote"], 1)]], "lllrr")}
    <p>Einbezogen sind Nachwuchsspieler mit mindestens 900 Einsatzminuten in der letzten Saison vor dem Stichtag. <strong>Durchbruch</strong>
    heißt: Der Spieler steht heute im Kader eines Klubs der Bundesliga oder 2. Liga, oder er ist Stammspieler in einer Regionalliga
    (mindestens 900 Minuten in Fenster 1, mindestens 300 Minuten in Fenster 2, weil die Saison 2026/27 erst zu einem Drittel gespielt ist).</p>
    {P.figur("Anteil der Spieler mit Durchbruch nach früherer Einstufung. Grün: Einstufung nach Talent-Rang, mit Unsicherheitsbereich. Grau: "
             "dieselbe Rechnung, wenn man nur nach Einsatzminuten reiht. Die gestrichelte Linie ist der Durchschnitt aller Spieler. Der "
             "Talent-Rang trennt in beiden Fenstern klar, am stärksten an der Spitze.", fig_talent())}
    {P.tabelle("Trefferquoten nach Einstufung. Lesebeispiel: Von den besten 10 % nach Talent-Rang schafften in Fenster 1 " +
               f"{t2['Top 10 %']['treffer']} von {t2['Top 10 %']['n']} den Durchbruch.", ["Einstufung", "Fenster 1", "Fenster 2", "Fenster 1, nur Minuten", "Fenster 2, nur Minuten"],
     [[k, f"{pct(t2[k]['quote'], 0)} ({t2[k]['treffer']} von {t2[k]['n']})", f"{pct(t2b[k]['quote'], 0)} ({t2b[k]['treffer']} von {t2b[k]['n']})",
       pct(m2[k]["quote"], 0), pct(m2b[k]["quote"], 0)] for k in ("Top 2 %", "Top 5 %", "Top 10 %", "Top 20 %", "20 bis 50 %", "untere Hälfte")] +
     [["alle", pct(T1["basisquote"], 0), pct(T2["basisquote"], 0), pct(T1["basisquote"], 0), pct(T2["basisquote"], 0)]], "lrrrr")}
    <p><strong>Was die Zahlen sagen.</strong> Die besten 2 % schaffen den Durchbruch rund dreimal so oft wie der Durchschnitt, die besten 10 %
    knapp doppelt so oft, die untere Hälfte deutlich seltener. Wer nur nach Einsatzminuten reiht, findet an der Spitze kaum mehr als
    Durchschnitt. Der Mehrwert kommt also aus der Bewertung, nicht aus der Spielzeit allein.</p>
    <p><strong>Die namentliche Probe</strong> steht in Abbildung 1: Von den zehn Bestbewerteten aus Fenster 1 haben {T1['topn'][0]['treffer']} den
    Durchbruch geschafft, unter den besten 30 sind es {T1['topn'][2]['treffer']}, unter den besten 50 {T1['topn'][3]['treffer']}.</p>
    <p><strong>Einordnung der oft zitierten 80 %.</strong> Die Fachliteratur nennt, dass die besten 20 % nach diesem Verfahren rund 80 % der
    später wertvollsten Spieler enthalten. In unseren Daten enthalten die besten 20 % {pct(t2['Top 20 %']['erfasst'], 0)} (Fenster 1) und
    {pct(t2b['Top 20 %']['erfasst'], 0)} (Fenster 2) der späteren Aufsteiger. Der Unterschied hat zwei Gründe: Unsere Stichprobe enthält nur
    Spieler, die bereits viel spielen, und der Beobachtungszeitraum ist mit zwei Jahren kurz. Für die Praxis ist die Trefferquote die
    wichtigere Zahl: Sie sagt, wie oft sich das Hinsehen lohnt.</p>
    {P.kernaussage("Kernaussagen", [f"Beste 2 %: {t2['Top 2 %']['treffer']} von {t2['Top 2 %']['n']} mit Durchbruch (Fenster 1), "
                                    f"{t2b['Top 2 %']['treffer']} von {t2b['Top 2 %']['n']} (Fenster 2). Durchschnitt: {pct(T1['basisquote'], 0)} und {pct(T2['basisquote'], 0)}.",
                                    f"Von den zehn Bestbewerteten spielen {T1['topn'][0]['profi']} in einer Profiliga.",
                                    "Einsatzminuten allein leisten das nicht. Der Mehrwert kommt aus der Bewertung."])}
    """)

    P.abschnitt("vorteil", "Warum das ohne Eventdaten funktioniert", f"""
    <p>Eventdaten beschreiben, was ein Spieler am Ball tut. Sie sind teuer in der Erhebung und deshalb nur für die oberen Ligen verfügbar.
    Das Plus-Minus-Verfahren braucht sie nicht, weil es am Ergebnis ansetzt und nicht an der Aktion.</p>
    {P.figur("Abdeckung. Eventdaten und Wettquoten enden an der Grenze zum Profifußball. Spielberichte gibt es für jedes Spiel jeder Liga. "
             "Genau dort, wo die meisten Spieler unentdeckt sind, ist das Verfahren einsetzbar.", fig_abdeckung())}
    {P.tabelle("Eventdaten und Ergebnisdaten im Vergleich.", ["", "Eventdaten", "Ergebnisdaten (dieses Verfahren)"], [
     ["Verfügbar für", "Profiligen und wenige Ligen darunter", "jede Liga mit Spielbericht, auch Nachwuchs"],
     ["Kosten je Spiel", "hoch, Erfassung durch Personen oder Kameras", "praktisch null, Spielberichte sind öffentlich"],
     ["Misst", "Aktionen am Ball", "Wirkung auf das Ergebnis"],
     ["Stärke", "erklärt, wie ein Spieler spielt", "erfasst auch Laufwege, Stellungsspiel und Defensivarbeit, die kein Event abbilden"],
     ["Schwäche", "bewertet, was sichtbar und zählbar ist", "braucht viele Spiele und sagt nicht, warum ein Spieler wirkt"],
     ["Beste Verwendung", "Profil und Spielstil", "Vorauswahl und Rangfolge"]], "lll", breit=True)}
    <p><strong>Der eigentliche Vorteil.</strong> Beide Datenarten ergänzen einander. Das Verfahren ersetzt nicht den Scout und nicht das
    Video. Es sagt, <em>bei wem</em> sich beides lohnt. In einem Markt mit über {de(round(N_SPIELER, -3))} Spielern ist das der Engpass:
    Niemand kann alle sehen. Abschnitt 7 zeigt, dass die Vorauswahl die Trefferquote an der Spitze etwa verdreifacht.</p>
    {P.kernaussage("Kernaussagen", ["Ergebnisdaten gibt es für jede Liga, Eventdaten nur für die oberen.",
                                    "Das Verfahren erfasst auch Wirkung, die kein Event abbildet, etwa Defensivarbeit.",
                                    "Es ersetzt Scout und Video nicht, sondern sagt, wo beides lohnt."])}
    """)

    P.abschnitt("grenzen", "Grenzen", f"""
    <p>Die Ergebnisse sind belastbar genug für eine Vorauswahl. Für eine Kaufentscheidung allein reichen sie nicht. Die wichtigsten
    Einschränkungen:</p>
    <ol>
    <li><strong>Kurzer Zeitraum.</strong> Die Daten beginnen 2023/24. Der längste mögliche Rückblick umfasst zwei Jahre. Ob ein Spieler sich
    im Profifußball hält, ist damit noch nicht messbar.</li>
    <li><strong>Kleine Fallzahlen an der Spitze.</strong> Die besten 2 % sind elf bis zwölf Spieler je Fenster. Die Abbildungen zeigen den
    Unsicherheitsbereich. Die Richtung ist in beiden Fenstern gleich, die genaue Höhe ist es nicht.</li>
    <li><strong>Durchbruch ist nur teilweise sichtbar.</strong> Profiligen und Ausland sind nicht Teil der Spieldaten. Der Profistatus stammt
    aus den öffentlichen Spielerprofilen des Verbands und kann veraltet sein. Spieler, die ins Ausland gewechselt sind, zählen als kein
    Durchbruch. Die wahren Quoten liegen eher höher. Ein Abgleich mit einer Datenbank zum Profifußball ist vorbereitet.</li>
    <li><strong>Akademie-Effekt.</strong> Spieler großer Akademien haben bessere Chancen, unabhängig von ihrer Bewertung. Ein Teil der
    Trefferquote geht darauf zurück. Der Vergleich innerhalb derselben Akademie steht noch aus.</li>
    <li><strong>Zweite Mannschaften.</strong> Ein Stammplatz in der zweiten Mannschaft eines Profiklubs in der Regionalliga zählt hier als
    Durchbruch. Man kann das auch als Vorstufe werten.</li>
    <li><strong>Wenig Einsatzzeit.</strong> Unter rund 900 Minuten ist ein Wert vorläufig. Das Dashboard zeigt das als Ampel.</li>
    <li><strong>Kein Ersatz für die Mannschaftsstärke.</strong> Für die Prognose des nächsten Spiels ist eine laufend aktualisierte
    Mannschaftsstärke besser. Die Spielerwerte beantworten eine andere Frage.</li>
    </ol>
    {P.figur("Unsicherheit an der Spitze, Fenster 1. Je kleiner die Gruppe, desto breiter der Bereich, in dem die wahre Trefferquote liegt. "
             "Auch die untere Grenze der besten 2 % liegt über dem Durchschnitt aller Spieler.", (lambda: (
        lambda fig_ax: (
            [fig_ax[1].plot([b_["ci"][0], b_["ci"][1]], [i, i], color=GREEN, lw=5, solid_capstyle="round", alpha=.35) for i, b_ in enumerate(T1["nach_talent"][:4])],
            [fig_ax[1].plot([b_["quote"]], [i], "o", color=GREEN, ms=7) for i, b_ in enumerate(T1["nach_talent"][:4])],
            [fig_ax[1].text(b_["ci"][1] + 1.5, i, f"{b_['treffer']} von {b_['n']}", va="center", fontsize=8) for i, b_ in enumerate(T1["nach_talent"][:4])],
            fig_ax[1].axvline(T1["basisquote"], color=CB, lw=1.1, ls=(0, (4, 3))),
            fig_ax[1].set_yticks(range(4)), fig_ax[1].set_yticklabels([b_["band"] for b_ in T1["nach_talent"][:4]]), fig_ax[1].invert_yaxis(),
            fig_ax[1].set_xlim(0, 105), fig_ax[1].set_xlabel("Anteil mit Durchbruch in %, Punkt = gemessen, Balken = Unsicherheitsbereich"),
            svg(fig_ax[0]))[-1])(plt.subplots(figsize=(7.4, 2.2))))())}
    {P.kernaussage("Kernaussagen", ["Zwei Jahre Rückblick, kleine Gruppen an der Spitze: Richtung gesichert, Höhe mit Unsicherheit.",
                                    "Wechsel ins Ausland und in Profiligen sind unvollständig erfasst, die wahren Quoten liegen eher höher."])}
    """)

    if not EXTERN:
        P.einordnung(
            anknuepfung={"daten": "Spielberichte des Verbands als eigene Quelle",
                         "trainer": "Gewinnwahrscheinlichkeit aus Quoten als Vorbild; hier von unten aus Spielerwerten aufgebaut",
                         "impact": "Spielerwert in Punkten für Ligen ohne Eventdaten",
                         "scouting": "Vorauswahl und Ratings für Data Checks aus dem Unterhaus"},
            konzepte=["Gewinnwahrscheinlichkeit aus Quoten", "Plus-Minus-Rating (RAPM)", "Spielerwert in Ligapunkten"],
            text_davor="<p>Interne Fassung. Zahlen aus validierung/studie.py, Dashboard in dashboard.html, Methodenpapier in docs/methodik.</p>")

    P.literatur({
     "Methode: Plus-Minus und Talent": [
      ("Hvattum, L. M. (2019).", "A comprehensive review of plus-minus ratings for evaluating individual players in team sports. <i>International Journal of Computer Science in Sport</i> 18(1), 1–23.", "Überblick"),
      ("Hvattum, L. M. (2020).", "Offensive and defensive plus-minus player ratings for soccer. <i>Applied Sciences</i> 10(20), 7345.", "Abschnitt 3"),
      ("Hvattum, L. M., Kriegl, M.-A. und Čulík, M. (2023).", "Identifying talent with plus-minus ratings in association football. In Y. Dominicy und C. Ley (Hrsg.), <i>Statistics Meets Sports</i>, 175–200. Cambridge Scholars.", "Peak-Wert, Talent-Rang, Abschnitt 6"),
      ("Kharrat, T., McHale, I. G. und López Peña, J. (2020).", "Plus-minus player ratings for soccer. <i>European Journal of Operational Research</i> 283(2), 726–736.", "Spielerwert in Punkten"),
      ("Arntzen, H. und Hvattum, L. M. (2021).", "Predicting match outcomes in association football using team ratings and player ratings. <i>Statistical Modelling</i> 21(5), 449–470.", "Abschnitt 5")],
     "Mannschaftsstärke, Wettquoten, Prognosegüte": [
      ("Hvattum, L. M. und Arntzen, H. (2010).", "Using ELO ratings for match result prediction in association football. <i>International Journal of Forecasting</i> 26(3), 460–470.", "Mannschaftsstärke"),
      ("Štrumbelj, E. (2014).", "On determining probability forecasts from betting odds. <i>International Journal of Forecasting</i> 30(4), 934–943.", "Quote und Wahrscheinlichkeit"),
      ("Wunderlich, F. und Memmert, D. (2018).", "The betting odds rating system: Using soccer forecasts to forecast soccer. <i>PLOS ONE</i> 13(6), e0198668.", "Quoten als Maßstab"),
      ("Epstein, E. S. (1969).", "A scoring system for probability forecasts of ranked categories. <i>Journal of Applied Meteorology</i> 8, 985–987.", "Prognosefehler"),
      ("Constantinou, A. C. und Fenton, N. E. (2012).", "Solving the problem of inadequate scoring rules for assessing probabilistic football forecast models. <i>Journal of Quantitative Analysis in Sports</i> 8(1).", "Prognosefehler")],
     "Öffentliche Quellen": [
      ("Österreichischer Fußball-Bund.", "Öffentliche Spielberichte und Spielerprofile der Bewerbe ab der Saison 2023/24, oefb.at.", "Ergebnisse, Aufstellungen, Tor-Minuten")]})


out = ROOT / "docs" / "paper"
name = ("Scouting-Dashboard_Study_v1_2026-11-17_external_EN" if EN else "Scouting-Dashboard_Studie_Fassung1_2026-11-17" + ("_extern" if EXTERN else ""))
P.html(out / f"{name}.html"); P.pdf(out / f"{name}.pdf")
print("OK", out / f"{name}.pdf")
