#!/usr/bin/env python3
"""Rueckblick-Pilot: Haette das Rating die spaeteren Aufsteiger frueh erkannt?

Vorgehen (ohne Blick in die Zukunft):
  1. Ratings NUR aus der Saison 2023/24 rechnen (plusminus.py auf gefilterten CSVs).
  2. Spieler nach diesem fruehen Rating einstufen (Talent-Perzentil im Jahrgang bzw. Total).
  3. Ergebnis zwei bis drei Jahre spaeter messen:
       - "Profi":  aktueller Bewerb laut OeFB-Profil = ADMIRAL Bundesliga oder ADMIRAL 2. Liga
       - "Stamm Erwachsene": >= 900 Minuten seit 2025/26 in Regionalliga (bzw. Landesliga) in unseren Daten
  4. Trefferquoten je Einstufung und Erfassungsquote ("wie viele der spaeteren Aufsteiger waren oben dabei").

Aufruf:  python3 validierung/rueckblick_pilot.py [--data data] [--work <tmp-ordner>]
Schreibt validierung/rueckblick_pilot_ergebnis.json und gibt eine Textauswertung aus.
"""
from __future__ import annotations
import argparse, csv, json, os, re, subprocess, sys, tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
YOUTH = re.compile(r"\bU\s?\d|jugend", re.I)
CUT = "2024-07-01"          # Ende der Lernsaison 2023/24
OUT_FROM = "2025-07-01"     # Ergebniszeitraum: ab Saison 2025/26


def iso(d: str) -> str:
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", d or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def tier(comp: str) -> int:
    """Grobe Liga-Stufe eines Erwachsenenbewerbs: 3 = Regionalliga, 4 = Landesliga-Ebene, 5 = Oberliga."""
    if "Regionalliga" in comp and not YOUTH.search(comp):
        return 3
    if "Oberliga" in comp:
        return 5
    return 4


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data"))
    ap.add_argument("--work", default=None)
    a = ap.parse_args()
    data = Path(a.data)
    work = Path(a.work or tempfile.mkdtemp(prefix="rueckblick_"))
    work.mkdir(parents=True, exist_ok=True)

    # ---- 1. Lernsaison herausfiltern -------------------------------------------------
    M = {}
    with open(data / "matches.csv", encoding="utf-8") as f:
        rd = csv.DictReader(f); mf = rd.fieldnames
        rows = list(rd)
    for r in rows:
        r["_iso"] = iso(r["date"]); M[r["match_id"]] = r
    early = {mid for mid, r in M.items() if r["_iso"] and r["_iso"] < CUT}
    with open(work / "matches.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=mf, extrasaction="ignore"); w.writeheader()
        w.writerows(r for r in rows if r["match_id"] in early)
    for name in ("players.csv", "events.csv"):
        with open(data / name, encoding="utf-8") as fi, open(work / name, "w", newline="", encoding="utf-8") as fo:
            rd = csv.reader(fi); w = csv.writer(fo); head = next(rd); w.writerow(head); i = head.index("match_id")
            for r in rd:
                if r[i] in early:
                    w.writerow(r)
    rat = work / "ratings_2324.csv"
    if not rat.exists():
        subprocess.run([sys.executable, str(ROOT / "plusminus.py"), "--players", str(work / "players.csv"),
                        "--events", str(work / "events.csv"), "--matches", str(work / "matches.csv"),
                        "-o", str(rat), "--ref-year", "2024"], check=True, cwd=ROOT)
    R = {r["player_id"]: r for r in csv.DictReader(open(rat, encoding="utf-8"))}

    # ---- 2. Einsaetze: Lernsaison (Kohorte) und Ergebniszeitraum ---------------------
    early_min_y = defaultdict(int); early_min_e = defaultdict(int)
    later = defaultdict(lambda: defaultdict(int))            # pid -> tier -> Minuten ab 2025/26 (Erwachsene)
    name = {}
    with open(data / "players.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pid = r["player_id"]
            if not pid:
                continue
            m = M.get(r["match_id"]);
            if not m or not m["_iso"]:
                continue
            mins = int(float(r["minutes"] or 0)); comp = m["competition"]; name[pid] = r["name"]
            if m["_iso"] < CUT:
                (early_min_y if YOUTH.search(comp) else early_min_e)[pid] += mins
            elif m["_iso"] >= OUT_FROM and not YOUTH.search(comp):
                later[pid][tier(comp)] += mins

    # ---- 3. Profi-Status laut OeFB-Profil ---------------------------------------------
    prof = json.load(open(data / "players_profiles.json", encoding="utf-8"))
    def pro(pid):
        b = (prof.get(pid) or {}).get("bewerbe_aktuell") or ""
        return 1 if "ADMIRAL Bundesliga" in b else (2 if "ADMIRAL 2. Liga" in b else 0)

    def outcome(pid):
        p = pro(pid); rl = later[pid].get(3, 0); ll = later[pid].get(4, 0) + later[pid].get(5, 0)
        return {"profi": p, "rl_min": rl, "ll_min": ll,
                "durchbruch": bool(p or rl >= 900), "stamm_erw": bool(p or rl >= 900 or ll >= 1800)}

    def num(v):
        try: return float(v)
        except (TypeError, ValueError): return None

    res = {"cut": CUT, "out_from": OUT_FROM, "lernspiele": len(early)}

    # ---- 4a. Nachwuchs: Jahrgaenge 2005-2008, >= 900 Jugend-Minuten in 2023/24 -----------
    youth = []
    for pid, mn in early_min_y.items():
        r = R.get(pid)
        if not r or mn < 900:
            continue
        by = num(r["birth_year"]); pt = num(r["pct_talent"])
        if by is None or pt is None or not (2005 <= by <= 2008):
            continue
        youth.append({"id": pid, "name": name.get(pid, ""), "by": int(by), "min2324": mn, "pct_talent": pt,
                      "total": num(r["total"]), "peak": num(r["peak"]), **outcome(pid)})
    youth.sort(key=lambda x: x["pct_talent"])
    bands = [("Top 2 %", 0, 2), ("Top 5 %", 0, 5), ("Top 10 %", 0, 10), ("Top 20 %", 0, 20),
             ("20-50 %", 20, 50), ("untere Haelfte", 50, 100.01)]
    def table(group, key):
        out = []; tot_hits = sum(1 for x in group if x[key])
        for lab, lo, hi in bands:
            g = [x for x in group if lo <= x["pct_talent"] < hi or (lo == 0 and x["pct_talent"] <= hi)]
            h = sum(1 for x in g if x[key])
            out.append({"band": lab, "n": len(g), "treffer": h, "quote": round(100 * h / len(g), 1) if g else None,
                        "erfasst": round(100 * h / tot_hits, 1) if tot_hits else None})
        return {"n": len(group), "treffer_gesamt": tot_hits,
                "basisquote": round(100 * tot_hits / len(group), 1) if group else None, "baender": out}
    res["nachwuchs"] = {"durchbruch": table(youth, "durchbruch"), "stamm_erw": table(youth, "stamm_erw"),
                        "je_jahrgang": {str(y): table([x for x in youth if x["by"] == y], "durchbruch") for y in (2005, 2006, 2007, 2008)},
                        "top30": youth[:30]}

    # ---- 4b. Erwachsene: bis 23 J. (Jg. >= 2001), >= 1800 Min. in 2023/24, Rang nach Total --
    adults = []
    for pid, mn in early_min_e.items():
        r = R.get(pid)
        if not r or mn < 1800:
            continue
        by = num(r["birth_year"]); tot = num(r["total"])
        if by is None or tot is None or by < 2001:
            continue
        adults.append({"id": pid, "name": name.get(pid, ""), "by": int(by), "min2324": mn, "total": tot, **outcome(pid)})
    adults.sort(key=lambda x: -x["total"])
    for i, x in enumerate(adults):
        x["pct_talent"] = 100 * i / max(1, len(adults))       # Rang nach Total als Perzentil (0 = bester)
    res["erwachsene"] = {"profi": table([dict(x, hit=bool(x["profi"])) for x in adults], "hit"), "top30": adults[:30]}

    out = ROOT / "validierung" / "rueckblick_pilot_ergebnis.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    def show(title, t):
        print(f"\n{title}: {t['n']} Spieler, {t['treffer_gesamt']} Treffer (Basisquote {t['basisquote']} %)")
        for b in t["baender"]:
            print(f"   {b['band']:<15} n={b['n']:>4}  Treffer {b['treffer']:>3}  Quote {b['quote']} %   erfasst {b['erfasst']} % aller Treffer")
    show("NACHWUCHS 2023/24 -> Durchbruch (Profi oder >= 900 Min. Regionalliga ab 2025/26)", res["nachwuchs"]["durchbruch"])
    show("NACHWUCHS 2023/24 -> Stamm im Erwachsenenfussball (zusaetzlich >= 1800 Min. Landesliga/Oberliga)", res["nachwuchs"]["stamm_erw"])
    for y, t in res["nachwuchs"]["je_jahrgang"].items():
        show(f"  Jahrgang {y}", t)
    print("\nTop 30 Nachwuchs nach fruehem Talent-Perzentil:")
    for x in youth[:30]:
        o = "BUNDESLIGA" if x["profi"] == 1 else "2. LIGA" if x["profi"] == 2 else (f"RL {x['rl_min']}'" if x["rl_min"] >= 900 else f"- (RL {x['rl_min']}', LL {x['ll_min']}')")
        print(f"   {x['name'][:28]:28} {x['by']}  P{x['pct_talent']:<5} peak {x['peak']:+.3f}  -> {o}")
    show("ERWACHSENE bis 23 J. in 2023/24 -> heute Profi (Bundesliga/2. Liga)", res["erwachsene"]["profi"])
    print("\nTop 30 Erwachsene nach fruehem Total:")
    for x in adults[:30]:
        o = "BUNDESLIGA" if x["profi"] == 1 else "2. LIGA" if x["profi"] == 2 else f"- (RL {x['rl_min']}', LL {x['ll_min']}')"
        print(f"   {x['name'][:28]:28} {x['by']}  total {x['total']:+.3f}  -> {o}")
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
