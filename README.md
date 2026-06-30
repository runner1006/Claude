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
  Verein, Bewerb; Profil-Verlinkung.
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

# 1) Spiel-IDs eines Bewerbs sammeln (Liga finden: --list)
python collect_ids.py --list
python collect_ids.py --bewerb 226374 --rounds 1-4 -o data/all_ids.txt

# 2) Spielberichte scrapen -> data/matches.json (+ CSVs)
python oefb_scraper.py --ids-file data/all_ids.txt --delay 1.0 --out-dir data

# 3) Spieler-Alter + Spielminuten -> data/players.csv (Cache: nur neue laden)
python player_ages.py --ids-file data/all_ids.txt -o data/players.csv \
       --cache players_cache.json
```

### Die drei Skripte

| Skript | Zweck |
|--------|-------|
| `collect_ids.py` | Findet Spiel-IDs eines Bewerbs über die Datenservice-REST-API. `--list` zeigt alle Bewerbe. |
| `oefb_scraper.py` | Scrapt Spielberichte (löst den Anubis-Bot-Schutz per Proof-of-Work, parst die eingebettete Aufstellung/Events). Schreibt `matches.json` + CSVs. |
| `player_ages.py` | Holt je Spieler Geburtsjahr (→ Alter) und berechnet Spielminuten aus der Wechsel-Timeline. Cacht Geburtsdaten (`has_age` / `partition_ids`), sodass bei neuen Runden nur neue Spieler geladen werden. |

## Datenstand

Aktuell enthalten (`data/`): 7 Bewerbe der Saison 2025/26, je 4 Runden —
Regionalliga Mitte, Landesliga Steiermark, Oberliga Nord / Mitte-West / Süd-Ost,
ÖFB Jugendliga U18 und Jugendregionalliga U18 (≈ 200 Spiele, ≈ 2.000 Spieler).

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
