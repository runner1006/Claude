# ÖFB Daten-Dashboard & Scraper

Toolkit, um Spielberichte des österreichischen Fußballbundes (oefb.at / STFV) zu
scrapen und in einem interaktiven, eigenständigen HTML-Dashboard auszuwerten —
inklusive Spieler-Alter, Spielminuten und Filtern. Online deploybar als Static
Site (z. B. render.com).

## Live-Dashboard (Deployment)

Das Dashboard ist eine **einzelne HTML-Datei** ohne Backend. Es lädt
`data/matches.json` und `data/players.csv` per `fetch` von derselben Origin.

### render.com (Blueprint)

1. Repo auf GitHub pushen (siehe unten).
2. In render.com: **New +** → **Blueprint** → dieses Repo wählen.
3. `render.yaml` wird erkannt → Static Site ohne Build, `/` zeigt das Dashboard.

Alternativ manuell als **Static Site**: Build Command leer, Publish Directory `.`.

> Funktioniert genauso auf GitHub Pages, Netlify oder Cloudflare Pages — es sind
> reine statische Dateien.

### Lokal ansehen

```bash
python3 -m http.server 8000      # im Repo-Verzeichnis
# -> http://localhost:8000/dashboard.html
```

## Dashboard-Funktionen

- **Matches** — filter-/sortierbare Spielliste; aufklappbares Detail mit beiden
  Aufstellungen (Alter + Spielminuten pro Spieler), Toren, Karten, Wechseln.
- **Spieler** — pro Spieler aggregiert (Gesamt-Minuten/-Tore/-Spiele), Alter,
  Verein, Bewerb; Klick auf den Namen öffnet das Profil.
- **Profil** — Einzelspieler-Seite (Suche oder Klick aus Spieler/Ratings):
  Foto, Nationalität, Karriere-Summen, Rating-Badges; Minuten-Split
  **Nachwuchs vs. Erwachsene**; Saison-Tabelle (Team, Minuten, Tore, roh +/-);
  **Plus-Minus-Verlauf** Match für Match mit minutengewichtetem Running Average
  (Kontext, um dem Modell-Rating zu vertrauen); alle Einsätze mit Gegner/Ergebnis;
  Vereins- & Saison-Historie aus dem ÖFB-Profil (`data/player_extras.json`,
  erzeugt via `python build_extras.py` nach `player_ages.py`).
- **Statistik** — Ø Alter & Ø Minuten je Verein / Bewerb / Kategorie / Position /
  Rolle / Jahrgang, sortierbar, mit Balken.
- **Filter** in einer Sidebar (Tabelle immer sichtbar): Multiselect-Dropdowns,
  Ja/Nein, und **Histogramm-Dual-Slider** (Dichtediagramm) mit manueller Eingabe.
  Kategorie-Filter trennt **Jugend** (U18) von **Erwachsenen**-Ligen.

Die Dichte-Slider stecken in der wiederverwendbaren Komponente
[`histogram-range.js`](histogram-range.js) (`HistogramRange({values, scale, …})`).

## Datenpipeline (3 Schritte)

```bash
pip install -r requirements.txt

# 1) Spiel-IDs sammeln
#    a) einzelner Bewerb, bestimmte Runden (Liga finden: --list):
python collect_ids.py --bewerb 226374 --rounds 1-4 -o data/all_ids.txt
#    b) volle Saison aller aktuell enthaltenen 7 Ligen:
python collect_all.py -o data/all_ids.txt

# 2) Spielberichte scrapen -> data/matches.json (+ CSVs)
python oefb_scraper.py --ids-file data/all_ids.txt --delay 1.0 --out-dir data

# 3) Spieler-Profile + Alter + Spielminuten -> data/players.csv
#    (+ data/players_profiles.json; Cache: nur neue Profile laden)
python player_ages.py --ids-file data/all_ids.txt -o data/players.csv \
       --cache data/profiles_cache.json --delay 0.5
```

### Die Skripte

| Skript | Zweck |
|--------|-------|
| `collect_ids.py` | Findet Spiel-IDs eines Bewerbs über die Datenservice-REST-API. `--list` zeigt alle Bewerbe. |
| `collect_all.py` | Sammelt die **volle Saison** aller 7 aktuell enthaltenen Ligen (feste Bewerb-IDs) dedupliziert in eine ID-Datei. |
| `oefb_scraper.py` | Scrapt Spielberichte (löst den Anubis-Bot-Schutz per Proof-of-Work, parst die eingebettete Aufstellung/Events). Schreibt `matches.json` + CSVs. |
| `player_ages.py` | Holt je Spieler das **volle Profil** (`parse_profile`) → Alter, Nationalität, Verein, Größe/Gewicht, Karriere-Vereine, Karriere-Statistik, Erfolge, Foto … und berechnet Spielminuten aus der Wechsel-Timeline. Skalare Felder → `players.csv`, reiche Rohdaten → `players_profiles.json`. Cacht ganze Profile, sodass nur neue Spieler geladen werden. |
| `plusminus.py` | Berechnet **Regularized-Adjusted-Plus-Minus-Ratings** (offensiv/defensiv/total + Peak) nach Hvattum/Kriegl/Čulík. Zerlegt Spiele in Segmente konstanter Aufstellung, löst ein ridge-regularisiertes Kleinste-Quadrate-System (`scipy.sparse` + `lsqr`) und rankt Spieler je Geburtsjahrgang in Perzentile (Talent-Filter). → `data/ratings.csv`. |

### Plus-Minus-Ratings (Talent-Identifikation)

```bash
pip install -r requirements.txt   # inkl. numpy/scipy
python plusminus.py               # nutzt data/*.csv -> data/ratings.csv (Lambda per CV)
```

`ratings.csv` je Spieler: `off`, `def`, `total`, `peak` (auf Leistungshoch
projiziert via fixer Alterskurve), sowie Perzentil-Ränge je Jahrgang
(`pct_total`, `pct_peak`, `pct_talent` = Peak+Minuten kombiniert, 0 = bester).
Methodik-Grundlage: Hvattum (2020); Hvattum, Kriegl & Čulík (2021).
**Hinweis:** aktuell nur eine Saison → Ratings sind verrauscht; die Alterskurve
ist fest übernommen, nicht geschätzt. Für robuste Werte mehr Saisons scrapen.

### Spieler-Profilfelder (neu in `players.csv`)

Zusätzlich zu `birth_year`/`age`/`minutes`/`goals`: `nationalitaet`, `verband`
(Landesverband-Kürzel), `profil_verein`, `groesse`, `gewicht`, `nachwuchs`,
`blueCards`, `foto_url`, `erstes_spiel`, `letztes_spiel`, `anzahl_vereine`,
`bewerbe_aktuell` sowie die Karrieresummen `karriere_spiele`, `karriere_tore`,
`karriere_minuten`, `karriere_siege/unentschieden/niederlagen`,
`karriere_gelbe/gelbrote/rote`. Die verschachtelten Rohdaten (Karriere-Vereine,
Statistik je Kategorie, Erfolge, Bewerbe) stehen je Spieler in
`data/players_profiles.json`.

## Datenstand

Aktuell enthalten (`data/`): 7 Bewerbe der Saison 2025/26, **komplette Saison** —
Regionalliga Mitte (30 Runden), Landesliga Steiermark (30), Oberliga Nord /
Mitte-West / Süd-Ost (je 26), ÖFB Jugendliga U18 (22) und Jugendregionalliga U18
(26); zusammen ≈ 1.300 Spiele. Je Spieler inkl. vollem Profil (Nationalität,
Verein, Karriere-Statistik, Erfolge …).

Bewerb-IDs: Regionalliga Mitte `226374`, Landesliga Steiermark `226282`,
Oberliga Nord `226273`, Oberliga Mitte West `226278`, Oberliga Süd Ost `226272`,
ÖFB Jugendliga U18 `227230`, ÖFB Jugendregionalliga U18 `227253`.

### Neue Daten erzeugen

`collect_ids.py --bewerb <ID> --rounds <a-b>` für weitere Ligen/Runden, dann
Schritte 2 + 3. IDs in `data/all_ids.txt` zusammenführen (dedupliziert), erneut
scrapen und `player_ages.py` laufen lassen — der Cache lädt nur neue Profile.

## Hinweise

- Fair scrapen: `--delay` nicht auf 0 setzen, Nutzungsbedingungen von oefb.at
  beachten. Nicht existierende IDs werden übersprungen (`ok=false`).
- Geburtsdaten sind öffentlich nur als **Jahr** hinterlegt (Tag = 1.1.); das Alter
  ist daher jahresbasiert (±1 Jahr). Fehlende Daten (`geburtsdatum=0`) werden als
  *unbekannt* behandelt, nicht als Jahrgang 1970.
