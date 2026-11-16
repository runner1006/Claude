# -*- coding: utf-8 -*-
"""Machbarkeitsprobe: OEFB-Spieler mit der Scoutastic-API (LASK-Instanz) verknuepfen.

Nur lesend, nur GET. Das Token wird nie ausgegeben und nie geschrieben.

Aufruf:
    python3 validierung/scoutastic_probe.py            # Stichprobe ziehen, abgleichen, JSON schreiben
    python3 validierung/scoutastic_probe.py --offline  # nur aus dem Cache, kein Request

Zugang (in dieser Reihenfolge):
    1. Umgebungsvariable SCOUTASTIC_API_TOKEN
    2. Datei aus der Umgebungsvariable SCOUTASTIC_ENV
    3. ~/zugaenge/scoutastic.env   (Zeile SCOUTASTIC_API_TOKEN=...)

Ablauf des Abgleichs (die API hat keine Namenssuche per GET):
    OEFB-Verein -> Scoutastic-Stammverein (Teamliste, offline)
    -> Kandidatenpool je Stammverein: GET /players/team/{id}?includeClubTeams=true
       plus Abgaenge GET /players/transfers?from={tmId}&date=...
    -> Treffer ueber normalisierten Namen + Geburtsjahr (OEFB kennt nur das Jahr)
    -> Werdegang: GET /players/{id}?performanceSummary=true&marketValues=true
"""
import gzip
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://lask.scoutastic.com/api/v1"
REPO = Path(__file__).resolve().parent.parent
PAUSE = 0.35            # Sekunden zwischen zwei Requests
MAX_REQUESTS = int(os.environ.get("SCOUTASTIC_MAX_REQUESTS", "150"))
OFFLINE = "--offline" in sys.argv

_TOKEN = None
N_REQ = 0
REQ_LOG = []            # (Pfad ohne Geheimnisse, Status, Sekunden)
PATHS = set()           # verschiedene Pfade dieses Laufs = Requests bei leerem Cache


# ------------------------------------------------------------------ Zugang

def _data_dir() -> Path:
    """Cache der Rohantworten: ausserhalb des Repos (enthaelt Vertragsfelder)."""
    env = os.environ.get("SCOUTASTIC_PROBE_DATEN")
    base = Path(env) if env else Path.home() / "daten" / "scoutastic-probe"
    return base / "oefb_validierung"


def _token() -> str:
    global _TOKEN
    if _TOKEN:
        return _TOKEN
    t = os.environ.get("SCOUTASTIC_API_TOKEN")
    if not t:
        cands = []
        if os.environ.get("SCOUTASTIC_ENV"):
            cands.append(Path(os.environ["SCOUTASTIC_ENV"]))
        cands.append(Path.home() / "zugaenge" / "scoutastic.env")
        for f in cands:
            if f.is_file():
                for line in f.read_text(encoding="utf-8").splitlines():
                    if line.strip().startswith("SCOUTASTIC_API_TOKEN"):
                        t = line.split("=", 1)[1].strip().strip("\"'")
                        break
            if t:
                break
    if not t:
        raise SystemExit("Kein Scoutastic-Token: SCOUTASTIC_API_TOKEN setzen oder "
                         "~/zugaenge/scoutastic.env anlegen.")
    _TOKEN = t
    return t


def get(path: str, cache: bool = True, retries: int = 3, timeout: int = 90):
    """Eine GET-Anfrage mit gzip-Cache, Zaehler und Pause. Nie eine andere Methode."""
    global N_REQ
    PATHS.add(path)
    cf = _data_dir() / (hashlib.sha1(path.encode()).hexdigest()[:20] + ".json.gz")
    if cache and cf.exists():
        with gzip.open(cf, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    if OFFLINE:
        raise RuntimeError(f"offline, nicht im Cache: {path}")
    if N_REQ >= MAX_REQUESTS:
        raise RuntimeError(f"Request-Budget {MAX_REQUESTS} erreicht")
    req = urllib.request.Request(BASE + path, method="GET", headers={
        "Authorization": f"Bearer {_token()}", "Accept": "application/json"})
    last = None
    for attempt in range(retries):
        N_REQ += 1
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8")          # nie auf Latin-1 zurueckfallen
                REQ_LOG.append((path, r.status, round(time.time() - t0, 2), len(raw)))
                d = json.loads(raw)
            time.sleep(PAUSE)
            if cache:
                cf.parent.mkdir(parents=True, exist_ok=True)
                with gzip.open(cf, "wt", encoding="utf-8") as fh:
                    json.dump(d, fh, ensure_ascii=False)
            return d
        except urllib.error.HTTPError as e:
            REQ_LOG.append((path, e.code, round(time.time() - t0, 2), 0))
            if e.code != 429 and 400 <= e.code < 500:
                raise RuntimeError(f"HTTP {e.code} bei GET {path}") from None
            last = f"HTTP {e.code}"
        except Exception as e:                           # Timeout, Verbindungsabbruch
            REQ_LOG.append((path, type(e).__name__, round(time.time() - t0, 2), 0))
            last = type(e).__name__
        time.sleep(2 ** attempt)
    raise RuntimeError(f"GET {path} fehlgeschlagen: {last}")


# ------------------------------------------------------------ Normalisierung

_TRANS = str.maketrans({"ß": "ss", "ø": "o", "đ": "d", "ł": "l", "æ": "ae", "ı": "i"})


def norm(s: str) -> str:
    """Kleinschreibung, Diakritika weg, Bindestrich = Leerzeichen."""
    s = (s or "").lower().translate(_TRANS)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def norm_de(s: str) -> str:
    """Wie norm(), aber Umlaute als ae/oe/ue (Transfermarkt schreibt teils so)."""
    s = (s or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue")):
        s = s.replace(a, b)
    return norm(s)


# ---------------------------------------------------------------- Stichprobe

HARD_CASES = {            # OEFB-ID -> warum schwierig
    "864048": "sehr haeufiger Name (Alexander Hofer, 4x in der OEFB-DB)",
    "816415": "haeufiger Name (Elias Neubauer, 3x in der OEFB-DB)",
    "463666": "zweiter Vorname (Felix Rudolf Wimmer)",
    "1007859": "Doppelname (Erik Baranyai-Ulvestad)",
    "1461988": "vierteiliger Name (Loiange Delphin Ondoa Belinga)",
}


def load_oefb():
    d = json.loads((REPO / "data" / "scout.json").read_text(encoding="utf-8"))
    ix = {c: i for i, c in enumerate(d["cols"])}
    txt = (REPO / "data" / "players_profiles.json").read_text(encoding="utf-8")
    prof = {}
    # Regex-Scan wie build_dashboard.py::load_birthdates, plus Profilverein und Namensteile
    for m in re.finditer(r'"(\d+)":\{"geburtsdatum":("[\d-]+"|null)', txt):
        chunk = txt[m.start(): m.start() + 4000]
        def f(key):
            mm = re.search(r'"%s":"([^"]*)"' % key, chunk)
            return mm.group(1) if mm else None
        prof[m.group(1)] = {
            "geburtsdatum": m.group(2).strip('"') if m.group(2) != "null" else None,
            "profil_verein": f("profil_verein"), "bewerbe_aktuell": f("bewerbe_aktuell"),
            "vorname": f("vorname"), "nachname": f("nachname")}
    return d, ix, prof


def build_sample():
    d, ix, prof = load_oefb()
    comps, teams = d["competitions"], d["teams"]

    def rec(r, gruppe):
        p = prof.get(r[0], {})
        return {"oefb_id": r[0], "name": r[1], "gruppe": gruppe,
                "vorname": p.get("vorname"), "nachname": p.get("nachname"),
                "geburtsjahr": r[ix["by"]], "geburtsdatum_oefb": p.get("geburtsdatum"),
                "oefb_teams": [teams[t] for t in r[ix["teams"]]],
                "oefb_bewerbe": [comps[c] for c in r[ix["comps"]]],
                "profil_verein": p.get("profil_verein"),
                "bewerbe_aktuell": p.get("bewerbe_aktuell"),
                "min": r[ix["min"]], "total": r[ix["total"]], "peak": r[ix["peak"]],
                "pct_talent": r[ix["pct_talent"]],
                "schwierig": HARD_CASES.get(r[0])}

    def is_youth(r):
        return any("ÖFB Jugendliga" in comps[c] or "Jugendregionalliga" in comps[c]
                   for c in r[ix["comps"]])

    rows = d["rows"]
    y = [r for r in rows if is_youth(r) and r[ix["by"]] and 2005 <= r[ix["by"]] <= 2008
         and (r[ix["min"]] or 0) >= 1800 and r[ix["pct_talent"]] is not None]
    y.sort(key=lambda r: (r[ix["pct_talent"]], -r[ix["total"]]))
    a = [r for r in rows if r[ix["by"]] and 1998 <= r[ix["by"]] <= 2004
         and (r[ix["min"]] or 0) >= 3000 and r[ix["total"]] is not None]
    a.sort(key=lambda r: -r[ix["total"]])
    out = [rec(r, "jugend") for r in y[:20]] + [rec(r, "erwachsen") for r in a[:10]]
    have = {s["oefb_id"] for s in out}
    out += [rec(r, "schwierig") for r in rows if r[0] in HARD_CASES and r[0] not in have]
    return out


# ------------------------------------------------- OEFB-Verein -> Scoutastic

_NOISE = set("""aka nwz spg sg fc sv sk sc sku skn ask asv usv tsv tsu fk fsc dsc svg ac wsc
u15 u16 u18 amat amateure juniors ii i km 1894 1902 1919 1921 akademie fussball fußball
rz pellets flyeralarm hypo oberbank guntamatic eglo licht loidl wonisch installationen
sparkasse stadtwerke raiffeisen sedda unis union intemann puntigamer dsm ertl glas
steiermark ooe oö nö no wien""".split())

# Handkorrekturen fuer die Stichprobe: OEFB-Schreibweise -> Scoutastic-Stammverein
ALIAS = {
    "wac": "Wolfsberger AC", "aka rz pellets wac u18": "Wolfsberger AC",
    "rz pellets wac": "Wolfsberger AC",
    "vienna": "First Vienna FC", "nwz first vienna fc 1894 u18": "First Vienna FC",
    "nwz first vienna fc 1894 u16": "First Vienna FC",
    "lask": "LASK", "lask akademie oo u18": "LASK",
    "junge wikinger ried": "SV Ried", "aka sv ried u18": "SV Ried", "aka sv ried u16": "SV Ried",
    "sv oberbank ried": "SV Ried", "sv guntamatic ried": "SV Ried",
    "aka fc flyeralarm admira u18": "Admira Wacker",
    "aka fc flyeralarm admira u16": "Admira Wacker",
    "aka hypo vorarlberg u18": "AKA Vorarlberg U18", "aka hypo vorarlberg u16": "AKA Vorarlberg U18",
    "aka hypo vorarlberg u15": "AKA Vorarlberg U18",
    "scr altach juniors": "SCR Altach", "scr altach juniors amateure": "SCR Altach",
    "gak 1902": "Grazer AK", "aka gak 1902 u18": "Grazer AK", "aka gak 1902 u16": "Grazer AK",
    "young violets austria wien": "FK Austria Wien", "aka fk austria wien u18": "FK Austria Wien",
    "aka fk austria wien u16": "FK Austria Wien",
    "austria klagenfurt": "SK Austria Klagenfurt",
    "aka sk austria klagenfurt u18": "SK Austria Klagenfurt",
    "aka sk austria klagenfurt u16": "SK Austria Klagenfurt",
    "ksv 1919": "SV Kapfenberg", "kapfenberger sv": "SV Kapfenberg",
    "fac wien": "Floridsdorfer AC", "volkermarkt": "VST Völkermarkt",
    "deutschlandsberg": "Deutschlandsberger SC",
    "dsc wonisch installationen": "Deutschlandsberger SC",
    "spg dsm fussball akademie oststeiermark u18": "AKA Oststeiermark U18",
    "sc diex 1986": "SC Diex", "sportunion mauer": "Union Mauer",
    "fc marchfeld donauauen mannsdorf grossenzersdorf": "FC Marchfeld Donauauen",
}


def load_sc_teams():
    """Teamliste der Instanz (115.667 Zeilen). Liegt als Cache vor; ein Neuabruf
    waere GET /teams?limit=1000 ueber ~118 Seiten und gehoert nicht in die Probe."""
    env = os.environ.get("SCOUTASTIC_PROBE_DATEN")
    base = Path(env) if env else Path.home() / "daten" / "scoutastic-probe"
    f = base / "teams_all.json.gz"
    if not f.exists():
        raise SystemExit(f"Teamliste fehlt: {f} (einmalig per GET /teams ernten)")
    with gzip.open(f, "rt", encoding="utf-8") as fh:
        t = json.load(fh)
    return t


def _core(name: str) -> frozenset:
    return frozenset(w for w in norm(name).split() if w not in _NOISE and len(w) > 2)


class ClubMap:
    def __init__(self):
        self.all_teams = load_sc_teams()
        self.team_by_tm = {t["transfermarktId"]: t for t in self.all_teams
                           if t.get("transfermarktId")}
        # Zuordnung nur gegen oesterreichische Teams (und solche ohne Landangabe)
        self.teams = [x for x in self.all_teams if x.get("country") in ("Austria", None)]
        self.by_name = {}
        for t in self.teams:
            self.by_name.setdefault(norm(t["name"]), t)
        self.by_core = {}
        for t in self.teams:
            if t.get("ageCategory") == "Senior" and t.get("league"):
                self.by_core.setdefault(_core(t["name"]), []).append(t)

    def resolve(self, oefb_name: str):
        """-> (Stammverein-Dokument | None, Art der Zuordnung)."""
        n = norm(oefb_name)
        if n in ALIAS:
            t = self.by_name.get(norm(ALIAS[n]))
            return (self._main(t), "alias") if t else (None, "alias ohne Team")
        if n in self.by_name:
            return self._main(self.by_name[n]), "exakt"
        c = _core(oefb_name)
        hits = self.by_core.get(c, []) if c else []
        mains = {(h.get("mainClubInternalId") or h["internalId"]) for h in hits}
        if len(mains) == 1:
            return self._main(hits[0]), "kern"
        return None, "mehrdeutig" if hits else "kein Team"

    def _main(self, t):
        mid = t.get("mainClubInternalId")
        if mid and mid != t["internalId"]:
            for x in self.teams:
                if x["internalId"] == mid:
                    return x
        return t

    def club_team_ids(self, main):
        """Alle Transfermarkt-IDs der Teams eines Stammvereins (fuer transfers?from=)."""
        mid = main["internalId"]
        return [(x["transfermarktId"], x["name"]) for x in self.teams
                if (x.get("mainClubInternalId") == mid or x["internalId"] == mid)
                and x.get("transfermarktId")]


# ------------------------------------------------------------------ Abgleich

def name_match(s, p) -> bool:
    """OEFB-Spieler s gegen Scoutastic-Spielerdokument p (oder Namensstring)."""
    full_sc = p if isinstance(p, str) else " ".join(
        str(p.get(k) or "") for k in ("firstName", "lastName", "alias", "homeCountryName"))
    last_sc = "" if isinstance(p, str) else (p.get("lastName") or "")
    for nf in (norm, norm_de):
        sc = set(nf(full_sc).split())
        o_last = set(nf(s.get("nachname") or s["name"].split()[-1]).split())
        o_first = set(nf(s.get("vorname") or s["name"].split()[0]).split())
        sc_last = set(nf(last_sc).split()) or sc
        # Nachname: ein Teil genuegt (Doppelnamen werden oft gekuerzt), aber er muss
        # im Scoutastic-NACHNAMEN stehen; Vorname: mindestens ein gemeinsamer Teil
        if (o_last & sc_last) and (o_first & sc):
            return True
    return False


def year_of(p):
    return p.get("yearOfBirth") or int((p.get("dateOfBirth") or "0000")[:4] or 0) or None


SINCE = 1656633600        # 01.07.2022 als Unix-Sekunden (transfers?date= will Sekunden)


def find_player(s, cm: "ClubMap"):
    """Sucht einen OEFB-Spieler in Scoutastic. -> dict mit status, methode, kandidaten."""
    clubs, seen, unmapped = [], set(), []
    for n in [s.get("profil_verein")] + list(reversed(s["oefb_teams"])):
        if not n:
            continue
        m, how = cm.resolve(n)
        if m is None:
            unmapped.append(n)
        elif m["internalId"] not in seen:
            seen.add(m["internalId"])
            clubs.append((m, how))
    res = {"vereine_zugeordnet": [m["name"] for m, _ in clubs],
           "vereine_ohne_zuordnung": unmapped, "requests_suche": 0}
    n0 = len(PATHS)
    cand, name_only, methode = {}, {}, None

    # Stufe 1: aktuelle Spielerliste je Stammverein (alle Teams des Klubs)
    for m, _ in clubs:
        pool = get(f"/players/team/{m['internalId']}?includeClubTeams=true&gender=male")
        for p in pool if isinstance(pool, list) else []:
            if name_match(s, p):
                (cand if year_of(p) == s["geburtsjahr"] else name_only)[p["internalId"]] = p
        if cand:
            methode = "vereinsliste"
            break

    # Stufe 2: Abgaenge der Teams dieser Klubs seit 2022 (Name), dann Jahrgang am Dokument
    if not cand:
        for m, _ in clubs:
            tids = [t for t in cm.club_team_ids(m)]
            tids.sort(key=lambda x: (" II" in x[1] or "Jugend" in x[1] or "Youth" in x[1]))
            for tid, _tn in tids[:4]:
                tr = get(f"/players/transfers?from={tid}&date={SINCE}&limit=1000")
                for t in tr.get("docs", []):
                    pid = t.get("playerInternalId")
                    if pid and pid not in cand and pid not in name_only \
                            and name_match(s, t.get("playerName") or ""):
                        p = get(f"/players/{pid}?marketValues=true&performanceSummary=true&debuts=true")
                        if not name_match(s, p):
                            continue
                        (cand if year_of(p) == s["geburtsjahr"] else name_only)[pid] = p
                if cand:
                    break
            if cand:
                methode = "abgaenge"
                break

    res["requests_suche"] = len(PATHS) - n0
    res["kandidaten_name_und_jahr"] = len(cand)
    res["kandidaten_nur_name"] = [
        {"name": f"{p.get('firstName')} {p.get('lastName')}", "jahr": year_of(p)}
        for p in name_only.values()]
    res["status"] = ("eindeutig" if len(cand) == 1 else
                     "mehrdeutig" if len(cand) > 1 else "nicht gefunden")
    res["methode"] = methode
    res["_cand"] = list(cand.values())
    return res


# ----------------------------------------------------------------- Werdegang

def load_competitions():
    """transfermarktId -> Liga-Stufe. Drei Requests, danach Cache."""
    out, page = {}, 1
    while True:
        d = get(f"/competitions?limit=1000&page={page}")
        for c in d.get("docs", []):
            out[c.get("transfermarktId")] = {
                "name": c.get("name"), "area": c.get("area"), "level": c.get("level"),
                "levelDefinition": c.get("levelDefinition"),
                "ageCategory": c.get("ageCategory")}
        if not d.get("hasNextPage"):
            return out
        page += 1


def is_pro_league(c) -> bool:
    return bool(c) and c.get("ageCategory") == "Senior" and c.get("level") in (1, 2)


def career(pid, comps, cm, extra=False):
    """Reduziert das Spielerdokument auf die Felder fuer den Abgleich.
    Vertragsende, Berater und Gehalt werden NICHT uebernommen (nur: Feld gefuellt?)."""
    p = get(f"/players/{pid}?marketValues=true&performanceSummary=true&debuts=true")
    team_by_tm = cm.team_by_tm
    seasons = []
    for season, rows in sorted((p.get("performanceSummary") or {}).items()):
        for e in rows:
            c = comps.get(e.get("competitionId")) or {}
            t = team_by_tm.get(str(e.get("teamId"))) or {}
            seasons.append({
                "saison": season, "bewerb_id": e.get("competitionId"),
                "bewerb": e.get("contest"), "land": c.get("area"),
                "stufe": c.get("level"), "stufe_text": c.get("levelDefinition"),
                "altersklasse": c.get("ageCategory"),
                "team_id": str(e.get("teamId")), "team": t.get("name"),
                # Zweitteam (Young Violets, Sturm II ...) nur fuer Erwachsenen-Ligen relevant
                "zweitteam": c.get("ageCategory") == "Senior" and c.get("level") in (1, 2, 3, 4)
                and bool(t.get("mainClubInternalId"))
                and t.get("mainClubInternalId") != t.get("internalId"),
                "spiele": e.get("matchesPlayed"), "minuten": e.get("minutesPlayed"),
                "startelf": (e.get("matchesPlayed") or 0) - (e.get("exchange") or 0),
                "tore": e.get("goals")})
    pro = [x for x in seasons if x["altersklasse"] == "Senior" and x["stufe"] in (1, 2)]
    best = max(pro, key=lambda x: x["minuten"] or 0, default=None)
    best_first = max((x for x in pro if not x["zweitteam"]),
                     key=lambda x: x["minuten"] or 0, default=None)
    mvh = p.get("marketValueHistory") or []
    out = {
        "internalId": p.get("internalId"), "transfermarktId": p.get("transfermarktId"),
        "vorname": p.get("firstName"), "nachname": p.get("lastName"),
        "geburtsdatum": (p.get("dateOfBirth") or "")[:10] or None,
        "nationalitaet": p.get("nationality"), "position": p.get("mainPosition"),
        "teams_aktuell": [{"name": t.get("name"), "tm_id": t.get("transfermarktId"),
                           "haupt": t.get("isMain"),
                           "liga": (team_by_tm.get(str(t.get("transfermarktId"))) or {}).get("league")}
                          for t in p.get("teams") or []],
        "leihe_von": (p.get("onLoanFrom") or {}).get("name") if isinstance(p.get("onLoanFrom"), dict) else None,
        "marktwert": p.get("marketValue"), "marktwert_max": max((m.get("marketvalue") or 0 for m in mvh), default=0),
        "marktwert_punkte": len(mvh),
        "feld_gefuellt": {k: bool(p.get(k)) and not str(p.get(k)).startswith("0001")
                          for k in ("contractExpires", "height", "foot", "agent",
                                    "optaId", "youthTeams", "debuts")},
        "debuts": [{"datum": (x.get("date") or "")[:10], "bewerb_id": x.get("competitionExternalId"),
                    "stufe": (comps.get(x.get("competitionExternalId")) or {}).get("level")}
                   for x in p.get("debuts") or []],
        "saisons": seasons,
        "profi_minuten_gesamt": sum(x["minuten"] or 0 for x in pro),
        "profi_beste_saison": best and {k: best[k] for k in ("saison", "bewerb_id", "team", "zweitteam", "minuten")},
        "profi_beste_saison_ohne_zweitteam": best_first and {k: best_first[k] for k in ("saison", "bewerb_id", "team", "minuten")},
        "aktualisiert": (p.get("updatedAt") or "")[:10],
    }
    out["durchbruch_stufe"] = (
        "B: >=900 min in 1./2. Liga (Kampfmannschaft)" if best_first and (best_first["minuten"] or 0) >= 900 else
        "B2: >=900 min in 2. Liga nur im Zweitteam" if best and (best["minuten"] or 0) >= 900 else
        "A: Profi-Einsatz (<900 min)" if out["profi_minuten_gesamt"] > 0 else
        "0: kein Profi-Einsatz")
    if extra:
        tr = get(f"/players/transfers/{pid}").get("docs", [])
        out["transfers"] = [{
            "datum": (t.get("date") or "")[:10], "von": (t.get("from") or {}).get("name"),
            "nach": (t.get("to") or {}).get("name"),
            "nach_bewerb": (t.get("to") or {}).get("competitionExternalId"),
            "nach_stufe": (comps.get((t.get("to") or {}).get("competitionExternalId")) or {}).get("level"),
            "leihe": t.get("isLoan"), "intern": t.get("isIntern")}
            for t in sorted(tr, key=lambda t: t.get("date") or "")]
        nt = get(f"/players/{pid}/national-team-history")
        out["nationalteams"] = [{"team": x.get("teamName"), "debuet": (x.get("debutDate") or "")[:10],
                                 "spiele": x.get("matches"), "tore": x.get("goals")}
                                for x in (nt if isinstance(nt, list) else [])]
    return out


# ---------------------------------------------------------------------- Lauf

def main():
    sample = build_sample()
    cm = ClubMap()
    comps = load_competitions()
    results = []
    for i, s in enumerate(sample):
        try:
            r = find_player(s, cm)
        except RuntimeError as e:
            r = {"status": "fehler", "fehler": str(e), "_cand": []}
        cands = r.pop("_cand")
        n1 = len(PATHS)
        # Transfers + Nationalteam nur fuer einen Teil (Request-Budget)
        extra = s["gruppe"] == "schwierig" or i % 3 == 0
        try:
            r["scoutastic"] = [career(p["internalId"], comps, cm, extra=extra) for p in cands]
        except RuntimeError as e:
            r["scoutastic"] = []
            r["fehler"] = str(e)
        r["requests_werdegang"] = len(PATHS) - n1
        results.append({**s, **r})
        sc = r["scoutastic"][0] if r["scoutastic"] else {}
        print(f"{i+1:2} {s['gruppe']:9} {s['name'][:30]:30} {s['geburtsjahr']} "
              f"{r['status']:14} {str(r.get('methode')):12} "
              f"{sc.get('geburtsdatum')} {sc.get('durchbruch_stufe', '')}", flush=True)
    from collections import Counter
    summary = {"n": len(results),
               "status": dict(Counter(r["status"] for r in results)),
               "status_je_gruppe": {g: dict(Counter(r["status"] for r in results if r["gruppe"] == g))
                                    for g in ("jugend", "erwachsen", "schwierig")},
               "methode": dict(Counter(str(r.get("methode")) for r in results)),
               "requests_bei_leerem_cache": len(PATHS),
               "requests_tatsaechlich_in_diesem_lauf": N_REQ,
               "erzeugt": time.strftime("%Y-%m-%d")}
    out = REPO / "validierung" / "scoutastic_probe_ergebnis.json"
    out.write_text(json.dumps({"zusammenfassung": summary, "spieler": results},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    print("geschrieben:", out.relative_to(REPO))


if __name__ == "__main__":
    main()
