# -*- coding: utf-8 -*-
"""Paper zum Scouting-Dashboard: Aufbau, Methode, Verbindung Spielerwert -> Gewinnwahrscheinlichkeit, Validierungsstudie.

Ein Generator, zwei Fassungen:
    python3 docs/paper/gen_dashboard_paper.py            -> interne Fassung (mit Einordnung und Dateiverweisen)
    python3 docs/paper/gen_dashboard_paper.py extern     -> externe Fassung (ohne Einordnung, ohne interne Spuren)
Zahlen kommen aus validierung/studie_ergebnis.json (validierung/studie.py) und data/matches.csv.
"""
import csv, json, re, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/strykerlabs-paper/scripts"))
sys.path.insert(0, str(Path.home() / ".claude/skills/strykerlabs-paper-extern/scripts"))
from paper import Paper
from paper_extern import PaperExtern
from figstyle import plt, svg, de, GREEN, CA, CB, CC, INK, MUTE, GRAU, HELLGRAU
from matplotlib.patches import FancyBboxPatch

EXTERN = len(sys.argv) > 1 and sys.argv[1] == "extern"
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
pct = lambda v, d=0: de(v, d) + " %"

def fig_aufbau():
    fig, ax = plt.subplots(figsize=(8.2, 3.3)); ax.set_axis_off(); ax.set_xlim(0, 100); ax.set_ylim(0, 42)
    for x, t in [(1, "Daten"), (26, "Modell"), (52, "Dashboard"), (80, "Entscheidung")]: ax.text(x, 40.5, t, fontsize=8, color=MUTE)
    box(ax, 1, 26, 19, 11, "Ergebnisse", "Endstand je Spiel")
    box(ax, 1, 13.5, 19, 11, "Aufstellungen", "wer spielte wann")
    box(ax, 1, 1, 19, 11, "Tor-Minuten", "wann fiel welches Tor")
    box(ax, 26, 20, 20, 13, "Spielerwert", "Plus-Minus, bereinigt um\nMitspieler und Gegner", fc=CA, tc="white")
    box(ax, 26, 4, 20, 13, "Mannschaftsstärke", "Startelf-Summe und\nErgebnisverlauf", fc=CA, tc="white")
    for y, t, s_ in [(29, "Scouting", "Filter, Vorlagen, Rangliste"), (19.5, "Spielerprofil", "drei Fragen, ein Urteil"),
                     (10, "Teams und Statistik", "Kader, Alter, Einsatz Junger"), (0.5, "Spiele", "Aufstellungen, Ereignisse")]:
        box(ax, 52, y, 22, 8, t, s_, fc=GREEN, tc="white", fs=7.8)
    box(ax, 80, 26, 19, 11, "Verpflichten", "wen beobachten,\nwen holen", fc="white", ec=GREEN)
    box(ax, 80, 13.5, 19, 11, "Fördern", "wer ist bereit für\nden nächsten Schritt", fc="white", ec=GREEN)
    box(ax, 80, 1, 19, 11, "Einordnen", "wie stark ist ein\nTeam wirklich", fc="white", ec=GREEN)
    for y in (31.5, 19, 6.5): arrow(ax, (20.4, y), (25.6, 26.5 if y > 10 else 10.5))
    for y in (33, 23.5, 14, 4.5): arrow(ax, (46.4, 26.5 if y > 15 else 10.5), (51.6, y))
    for y0, y1 in [(33, 31.5), (23.5, 19), (14, 6.5)]: arrow(ax, (74.4, y0), (79.6, y1))
    return svg(fig)

def fig_daten():
    fig, ax = plt.subplots(figsize=(7.4, 2.6))
    e = [SE[s] for s in SEASONS]; j = [SJ[s] for s in SEASONS]
    ax.bar(SEASONS, e, color=CA, width=.6, label="Erwachsenenfußball"); ax.bar(SEASONS, j, bottom=e, color=GREEN, width=.6, label="Nachwuchs")
    for i in range(len(SEASONS)): ax.text(i, e[i] + j[i] + 70, de(e[i] + j[i]), ha="center", fontsize=8)
    ax.set_ylabel("ausgewertete Spiele"); ax.set_ylim(0, max(a + b for a, b in zip(e, j)) * 1.18); ax.legend(loc="upper left", fontsize=7.5, ncol=2)
    ax.text(len(SEASONS) - 1, -0.16 * ax.get_ylim()[1], "laufende Saison", ha="center", fontsize=7, color=MUTE)
    return svg(fig)

def fig_segmente():
    fig, ax = plt.subplots(figsize=(7.6, 2.5)); ax.set_axis_off(); ax.set_xlim(-12, 100); ax.set_ylim(0, 30)
    X = lambda m: m / 90 * 96
    for a, b_, t, c in [(0, 58, "Abschnitt 1: 0. bis 58. Minute", "#eef5f2"), (58, 90, "Abschnitt 2: 58. bis 90. Minute", "#e3efe9")]:
        ax.add_patch(FancyBboxPatch((X(a) + .4, 4), X(b_) - X(a) - .8, 20, boxstyle="round,pad=0.1,rounding_size=0.8", fc=c, ec="#cfd8d4", lw=.8))
        ax.text((X(a) + X(b_)) / 2, 26.5, t, ha="center", fontsize=7.6, color=MUTE)
    ax.text(-11, 18, "Heim", fontsize=8.4, fontweight="bold"); ax.text(-11, 9, "Gast", fontsize=8.4, fontweight="bold")
    for x_, y_, t in [(X(29), 18, "Spieler A, B, C …"), (X(74), 18, "A, B und der Neue D"), (X(29), 9, "elf Gegenspieler"), (X(74), 9, "elf Gegenspieler")]:
        ax.text(x_, y_, t, ha="center", va="center", fontsize=7.8, bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="#b9c4bf", lw=.8))
    ax.plot([X(58), X(58)], [3, 25], color=CB, lw=1.3, ls=(0, (4, 3))); ax.text(X(58), 1, "Wechsel: C geht, D kommt", ha="center", fontsize=7.4, color=CB)
    for m_, y_ in [(23, 21.6), (71, 21.6), (80, 12.6)]: ax.text(X(m_), y_, "Tor", ha="center", fontsize=7, color="white", bbox=dict(boxstyle="round,pad=0.25", fc=GREEN, ec="none"))
    return svg(fig)

def fig_kette():
    fig, ax = plt.subplots(figsize=(8.2, 3.2)); ax.set_axis_off(); ax.set_xlim(0, 100); ax.set_ylim(0, 40)
    ax.text(1, 37.5, "Profifußball: von oben, über den Markt", fontsize=8, color=MUTE)
    box(ax, 1, 25, 21, 9.5, "Wettquoten", "viele Marktteilnehmer")
    box(ax, 39, 25, 22, 9.5, "Gewinnwahrscheinlichkeit", "je Spiel", fc=GREEN, tc="white", fs=8)
    box(ax, 78, 25, 21, 9.5, "erwartete Punkte", "je Spiel und Saison", fc="white", ec=GREEN)
    arrow(ax, (22.4, 29.7), (38.6, 29.7)); arrow(ax, (61.4, 29.7), (77.6, 29.7))
    ax.text(30.5, 31.3, "Quote umrechnen", ha="center", fontsize=6.6, color=MUTE)
    ax.text(1, 19.5, "Unterhalb der Profiligen: von unten, über die Spieler", fontsize=8, color=MUTE)
    box(ax, 1, 4, 16, 11, "Spielerwerte", "Tore je 90 Minuten", fc=CA, tc="white")
    box(ax, 21, 4, 16, 11, "Startelf-Stärke", "Summe der elf Werte", fc=CA, tc="white")
    box(ax, 41, 4, 18, 11, "Tordifferenz", "erwartet, je Spiel", fc=CA, tc="white")
    box(ax, 63, 4, 16, 11, "Sieg, Remis,\nNiederlage", "", fc=GREEN, tc="white", fs=7.6)
    box(ax, 83, 4, 16, 11, "Punkte", "je Spiel und Saison", fc="white", ec=GREEN)
    for a_, b_ in [(17.4, 20.6), (37.4, 40.6), (59.4, 62.6), (79.4, 82.6)]: arrow(ax, (a_, 9.5), (b_, 9.5))
    arrow(ax, (50, 24.4), (68, 15.6), c=GREEN, ls=(0, (3, 2))); ax.text(61.5, 20.6, "dieselbe Größe", fontsize=6.8, color=GREEN, ha="left")
    return svg(fig)

def fig_fuenftel():
    Q = B["fuenftel"]; fig, ax = plt.subplots(figsize=(7.4, 3.0))
    lab = ["klar schwächer", "etwas schwächer", "etwa gleich", "etwas stärker", "klar stärker"]
    h = [q["heim"] for q in Q]; r_ = [q["remis"] for q in Q]; g = [q["gast"] for q in Q]; x = range(5)
    ax.bar(x, h, color=GREEN, width=.62, label="Heimsieg"); ax.bar(x, r_, bottom=h, color=GRAU, width=.62, label="Remis")
    ax.bar(x, g, bottom=[a + b_ for a, b_ in zip(h, r_)], color=CB, width=.62, label="Auswärtssieg")
    for i, q in enumerate(Q):
        ax.text(i, h[i] / 2, pct(h[i]), ha="center", va="center", color="white", fontsize=8.5, fontweight="bold")
        ax.text(i, 104, f"{de(q['ppg'], 2)} Punkte", ha="center", fontsize=8)
    ax.set_xticks(list(x)); ax.set_xticklabels(lab); ax.set_ylim(0, 116); ax.set_yticks([0, 25, 50, 75, 100]); ax.set_ylabel("Anteil der Spiele in %")
    ax.set_xlabel("Startelf der Heimmannschaft im Vergleich zum Gegner, nach Spielerwerten vor Saisonbeginn")
    ax.legend(loc="upper center", bbox_to_anchor=(.5, -0.24), ncol=3, fontsize=7.5)
    return svg(fig)

def fig_rps():
    E = B["test_erwachsene"]; J = B["test_jugend"]
    keys = ["Häufigkeitsregel", "Startelf-Stärke (Spieler-Ratings), Stand Stichtag", "Mannschaftsstärke, Stand Stichtag",
            "Mannschaftsstärke laufend (Team-Elo)", "Startelf-Stärke + Mannschaftsstärke laufend"]
    lab = ["einfache Regel\n(immer gleiche Quote)", "Spielerwerte\n(Stand vor der Saison)", "Mannschaftsstärke\n(Stand vor der Saison)",
           "Mannschaftsstärke\n(laufend aktualisiert)", "Spielerwerte +\nMannschaftsstärke"]
    col = [GRAU, CA, "#7aa5d6", "#7aa5d6", GREEN]
    fig, axs = plt.subplots(1, 2, figsize=(8.0, 3.0), sharey=False)
    for ax, R_, t, n in ((axs[0], E, "Erwachsenenfußball", B["n_test_erw"]), (axs[1], J, "Nachwuchs", B["n_test_jug"])):
        v = [R_[k]["rps"] for k in keys]; ax.barh(range(5), v, color=col, height=.62); ax.invert_yaxis()
        for i, x_ in enumerate(v): ax.text(x_ + .0006, i, de(x_, 4), va="center", fontsize=7.8)
        ax.set_yticks(range(5)); ax.set_yticklabels(lab if ax is axs[0] else [""] * 5, fontsize=7.4); ax.set_xlim(min(v) - .012, max(v) + .008)
        ax.set_title(f"{t} · {de(n)} Spiele der Saison 2026/27"); ax.set_xlabel("Prognosefehler (kleiner ist besser)"); ax.grid(axis="y", visible=False)
    fig.tight_layout()
    return svg(fig)

def fig_spielerwert():
    W = B["spielerwert"]["stufen"]; fig, ax = plt.subplots(figsize=(7.4, 2.6))
    x = [f"+{de(w['delta'], 2)}" for w in W]; v = [w["punkte_30"] for w in W]
    ax.bar(x, v, color=GREEN, width=.55)
    for i, w in enumerate(W): ax.text(i, v[i] + .15, f"+{de(v[i], 1)} Punkte\nSiegchance +{de(w['siegchance_pp'], 1)} PP", ha="center", fontsize=7.6, linespacing=1.3)
    ax.set_ylim(0, max(v) * 1.45); ax.set_xlim(-.6, len(W) - .4); ax.set_ylabel("zusätzliche Punkte in 30 Spielen"); ax.set_xlabel("Verbesserung der Startelf in Toren je 90 Minuten (Summe der Spielerwerte)")
    return svg(fig)

def fig_talent():
    fig, axs = plt.subplots(1, 2, figsize=(8.0, 3.1), sharey=True)
    for ax, T in zip(axs, (T1, T2)):
        tb = {b_["band"]: b_ for b_ in T["nach_talent"]}; mb = {b_["band"]: b_ for b_ in T["nach_minuten"]}
        bands = ["Top 2 %", "Top 10 %", "Top 20 %", "20 bis 50 %", "untere Hälfte"]; x = range(len(bands)); w = .38
        v = [tb[k]["quote"] for k in bands]; m_ = [mb[k]["quote"] for k in bands]
        lo = [v[i] - tb[k]["ci"][0] for i, k in enumerate(bands)]; hi = [tb[k]["ci"][1] - v[i] for i, k in enumerate(bands)]
        ax.bar([i - w / 2 for i in x], v, w, color=GREEN, label="nach Talent-Rang", yerr=[lo, hi], error_kw=dict(ecolor="#555", lw=.8, capsize=2))
        ax.bar([i + w / 2 for i in x], m_, w, color=GRAU, label="nur nach Einsatzminuten")
        for i in x: ax.text(i - w / 2, 2.5, pct(v[i]), ha="center", fontsize=7.4, color="white", fontweight="bold", rotation=90, va="bottom")
        ax.axhline(T["basisquote"], color=CB, lw=1.1, ls=(0, (4, 3))); ax.text(len(bands) - .45, 91, f"gestrichelt: Durchschnitt {pct(T['basisquote'], 1)}", ha="right", fontsize=7.2, color=CB)
        ax.set_xticks(list(x)); ax.set_xticklabels(["Top\n2 %", "Top\n10 %", "Top\n20 %", "20 bis\n50 %", "untere\nHälfte"], fontsize=7.6); ax.set_ylim(0, 100)
        ax.set_title(f"{T['label']}: {de(T['n'])} Spieler, Jahrgänge {T['jahrgaenge'][0]} bis {T['jahrgaenge'][1]}")
    axs[0].set_ylabel("Anteil mit Durchbruch in %"); axs[0].legend(loc="upper right", bbox_to_anchor=(1, .9), fontsize=7.4)
    fig.tight_layout()
    return svg(fig)

def fig_topn():
    fig, axs = plt.subplots(1, 2, figsize=(8.0, 2.6), sharey=True)
    for ax, T in zip(axs, (T1, T2)):
        n = [t["n"] for t in T["topn"]]; pr = [100 * t["profi"] / t["n"] for t in T["topn"]]; rl = [100 * (t["treffer"] - t["profi"]) / t["n"] for t in T["topn"]]
        x = range(len(n)); ax.bar(x, pr, color=GREEN, width=.6, label="Profiliga"); ax.bar(x, rl, bottom=pr, color=CA, width=.6, label="Stammspieler Regionalliga")
        for i, t in enumerate(T["topn"]): ax.text(i, pr[i] + rl[i] + 2.5, f"{t['treffer']} von {t['n']}", ha="center", fontsize=8)
        ax.axhline(T["basisquote"], color=CB, lw=1.1, ls=(0, (4, 3)))
        ax.set_xticks(list(x)); ax.set_xticklabels([f"beste {k}" for k in n]); ax.set_ylim(0, 108); ax.set_title(T["label"])
    axs[0].set_ylabel("Anteil mit Durchbruch in %"); axs[1].legend(loc="upper right", fontsize=7.4)
    fig.tight_layout()
    return svg(fig)

def fig_abdeckung():
    fig, ax = plt.subplots(figsize=(7.6, 2.9)); ax.set_axis_off(); ax.set_xlim(0, 100); ax.set_ylim(0, 36)
    rows = [("Bundesliga, 2. Liga", 22, 30, True), ("Regionalligen", 36, 23, False), ("Landesligen, Oberligen", 50, 16, False), ("Akademie- und Nachwuchsligen", 64, 9, False)]
    for t, w, y, ev in rows:
        x0 = 30 - w / 2 + 6
        ax.add_patch(FancyBboxPatch((x0, y), w, 5.4, boxstyle="round,pad=0.15,rounding_size=0.7", fc=(HELLGRAU if ev else GREEN), ec="none"))
        ax.text(x0 + w / 2, y + 2.7, t, ha="center", va="center", fontsize=7.8, color=(INK if ev else "white"), fontweight="bold")
    ax.text(76, 32.7, "Eventdaten üblich,\nWettmarkt vorhanden", fontsize=7.6, color=MUTE, va="center")
    ax.text(76, 17, "keine Eventdaten, kein Wettmarkt.\nSpielberichte liegen für jedes Spiel vor:\nErgebnis, Aufstellung, Wechsel, Tore.\nHier arbeitet das Dashboard.", fontsize=7.6, color=INK, va="center", linespacing=1.4)
    ax.plot([72, 72], [9, 28.4], color=GREEN, lw=2); ax.plot([72, 72], [30, 35.4], color=GRAU, lw=2)
    return svg(fig)

# ---------------------------------------------------------------- Paper
TITEL = "Bessere Spieler finden, wo es keine Eventdaten gibt"
UNTER = "Das Scouting-Dashboard für den österreichischen Amateur- und Nachwuchsfußball: Aufbau, Methode und Nachweis der Aussagekraft"
if EXTERN:
    P = PaperExtern(titel=TITEL, untertitel=UNTER, dokumenttyp="Studie", fassung=FASSUNG, stand=STAND, kurztitel="Scouting-Dashboard Amateur- und Nachwuchsfußball")
else:
    P = Paper(titel=TITEL, untertitel=UNTER, dokumenttyp="Studie", fassung=FASSUNG, stand=STAND, modul="oefb", kurztitel="Scouting-Dashboard Amateur- und Nachwuchsfußball")

t2 = {b_["band"]: b_ for b_ in T1["nach_talent"]}; t2b = {b_["band"]: b_ for b_ in T2["nach_talent"]}
m2 = {b_["band"]: b_ for b_ in T1["nach_minuten"]}; m2b = {b_["band"]: b_ for b_ in T2["nach_minuten"]}
E = B["test_erwachsene"]; W = {w["delta"]: w for w in B["spielerwert"]["stufen"]}; Q = B["fuenftel"]
K_R, K_EF, K_E, K_C, K_F = ("Startelf-Stärke (Spieler-Ratings), Stand Stichtag", "Mannschaftsstärke, Stand Stichtag",
                            "Mannschaftsstärke laufend (Team-Elo)", "Startelf-Stärke + Mannschaftsstärke laufend", "Häufigkeitsregel")

P.zusammenfassung(
    f"<p>Unterhalb der Profiligen gibt es weder Eventdaten noch Wettquoten. Es gibt aber für jedes Spiel einen Spielbericht mit Ergebnis, "
    f"Aufstellung, Wechseln und Tor-Minuten. Das Scouting-Dashboard macht daraus eine Bewertung für {de(N_RATING)} Spieler aus "
    f"{de(N_SPIELE)} Spielen in {D['bewerbe']} Bewerben seit 2023/24. Der Wert eines Spielers ist der Unterschied, den er für die "
    f"Tordifferenz seiner Mannschaft macht, bereinigt um Mitspieler und Gegner.</p>"
    f"<p>Zwei Prüfungen ohne Blick in die Zukunft belegen die Aussagekraft. <strong>Erstens</strong> sagt die Summe der Spielerwerte einer "
    f"Startelf Ergebnisse voraus: Ist die Heimelf klar stärker besetzt, gewinnt sie {pct(Q[4]['heim'])} der Spiele, ist sie klar schwächer, "
    f"nur {pct(Q[0]['heim'])}. Im Erwachsenenfußball sind die Spielerwerte dabei so treffsicher wie eine reine Mannschaftsstärke mit "
    f"demselben Wissensstand, und sie sagen zusätzlich, <em>welche</em> Spieler die Stärke ausmachen. Eine um 0,10 Tore je Spiel bessere "
    f"Startelf bringt rund {de(W[0.1]['punkte_30'], 1)} Punkte in 30 Spielen. <strong>Zweitens</strong> erkennt das Rating spätere Aufsteiger "
    f"früh: Von den besten 2 % des Nachwuchses schafften {t2['Top 2 %']['treffer']} von {t2['Top 2 %']['n']} binnen zwei Jahren den Durchbruch, "
    f"im Durchschnitt aller waren es {pct(T1['basisquote'], 0)}. Von den zehn bestbewerteten Nachwuchsspielern spielen heute "
    f"{T1['topn'][0]['profi']} in einer Profiliga.</p>")

P.abschnitt("problem", "Ausgangslage und Ziel", f"""<style>.kern{{break-inside:avoid}}</style>
<p>Wer Spieler aus der Regionalliga, einer Landesliga oder einer Akademie beurteilen will, steht vor einer Lücke. In den Profiligen
gibt es Eventdaten zu jedem Pass und Wettquoten zu jedem Spiel. Darunter gibt es beides nicht. Scouting stützt sich dort auf
Beobachtung vor Ort, auf Tore und auf Empfehlungen. Das ist teuer, lückenhaft und bevorzugt Stürmer, weil nur Tore gezählt werden.</p>
<p><strong>Ziel</strong> des Dashboards ist eine belastbare Vorauswahl: Aus Tausenden Spielern jene finden, bei denen sich das genaue
Hinsehen lohnt. Dafür muss die Bewertung drei Dinge leisten. Sie muss für <em>jede</em> Liga verfügbar sein, sie muss Verteidiger und
Mittelfeldspieler genauso erfassen wie Torschützen, und sie muss nachweislich etwas über die Zukunft sagen.</p>
{P.figur("Aufbau. Aus drei Angaben des Spielberichts rechnet das Modell Spielerwerte und Mannschaftsstärken. Das Dashboard macht sie "
         "in vier Bereichen zugänglich. Am Ende stehen drei Arten von Entscheidungen.", fig_aufbau())}
{P.tabelle("Die drei Fragen dieses Papiers.", ["Nr.", "Frage", "Antwort in Abschnitt"], [
 ["1", "Was kann das Dashboard, und wie ist es aufgebaut?", "2"],
 ["2", "Wie hängen Spielerwert, Mannschaftsstärke, Gewinnwahrscheinlichkeit und Punkte zusammen?", "3 und 4"],
 ["3", "Stimmen die Bewertungen? Sagen sie Ergebnisse und spätere Karrieren voraus?", "5 und 6"]], "lll")}
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
beantwortet genau das. Abschnitt 5 prüft, ob beide Sichten zum selben Ergebnis kommen.</p>
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
{P.figur(f"Die namentliche Probe. Von den zehn bestbewerteten Nachwuchsspielern aus Fenster 1 haben {T1['topn'][0]['treffer']} den Durchbruch "
         f"geschafft, {T1['topn'][0]['profi']} davon stehen im Kader eines Profiklubs. Unter den besten 30 sind es {T1['topn'][2]['treffer']}, "
         f"unter den besten 50 {T1['topn'][3]['treffer']}. Die gestrichelte Linie ist der Durchschnitt.", fig_topn())}
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
Niemand kann alle sehen. Abschnitt 6 zeigt, dass die Vorauswahl die Trefferquote an der Spitze etwa verdreifacht.</p>
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
name = "Scouting-Dashboard_Studie_Fassung1_2026-11-17" + ("_extern" if EXTERN else "")
P.html(out / f"{name}.html"); P.pdf(out / f"{name}.pdf")
print("OK", out / f"{name}.pdf")
