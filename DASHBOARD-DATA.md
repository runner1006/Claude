# Dashboard-Datenvertrag (seit November 2026)

Das Dashboard (`dashboard.html`) lädt **nicht mehr** `players.csv` (118 MB), `matches.json`
(61 MB) und `player_extras.json` in den Browser. Stattdessen liefert `build_dashboard.py`
(läuft in `update_all.py` nach `build_db.py`) kompakte, vorberechnete Daten:

| Quelle | Zweck | Größe | Wann laden |
|---|---|---|---|
| `GET /data/scout.json` | 1 Zeile je Spieler (Aggregat + Rating) – Tabs Scouting, Statistik, Profil-Suche | ~2,3 MB roh / 0,63 MB gzip | beim Start |
| `GET /data/matches_index.json` | 1 Zeile je Spiel ohne Aufstellung/Events – Tab Matches | ~2,5 MB roh / 0,53 MB gzip | erst beim Öffnen des Matches-Tabs |
| `GET /api/profile/{player_id}` | fertiges Profil (alle Einsätze mit rohem +/-, Jahrgangs-Referenz, Perzentile, Historie) | 2–6 KB gzip | beim Öffnen eines Profils |
| `GET /api/match/{match_id}` | Aufstellungen (mit Minuten, Jahrgang) + Events eines Spiels | ~5 KB | beim Aufklappen eines Spiels |
| `GET /api/health` | Zähler + `dashboard.built` | – | optional (Pill "Stand") |

Alle Antworten tragen `ETag` + `Cache-Control: no-cache` (Browser fragt nach, bekommt 304 wenn
unverändert). JSON der API wird per GZip-Middleware komprimiert; `/data/*.json` wird als
vor-gezipptes `.gz` mit `Content-Encoding: gzip` ausgeliefert (transparent für `fetch`).

## scout.json

```json
{"v":1,"built":"2026-11-03T01:52:10","ref_date":"2026-11-03",
 "stats":{"players":13167,"matches":11074,"appearances":371488,"ratings":11882,"bench_n":9076,"latest_match":"2026-10-31"},
 "teams":["ASK Ebreichsdorf", ...],          // Namens-Wörterbuch (Index -> Name)
 "competitions":["11teamsports 1. Landesliga", ...],
 "cols":["id","name","teams","comps","by","age","pos","role","nat","verband","cap","min","matches","goals",
         "first","last","off","def","total","peak","pct_talent","pct_total","pct_peak","r_min","r_matches"],
 "rows":[["463666","Felix Rudolf Wimmer",[140,353],[10],1998,28,"tor","starter","","O",false,3510,42,0,
          "2023-07-28","2025-10-31",0.0581,0.063,0.1211,0.1311,15.1,9.4,9.4,3510,39], ...]}
```

Spalten je Zeile (Reihenfolge = `cols`):

| Spalte | Bedeutung |
|---|---|
| `id` | ÖFB-Spieler-ID (String). `""` bei 20 Einsatzzeilen ohne ID (Bank, 0 Minuten) – dann kein Profil |
| `name` | Name |
| `teams` | Indizes in `teams`, **zuletzt gespielt zuerst** (bisher: Reihenfolge der CSV) |
| `comps` | Indizes in `competitions`, zuletzt gespielt zuerst |
| `by` | Jahrgang (int) oder `null` |
| `age` | Alter am `ref_date` aus dem Geburtsdatum (bisher: Alter zum Scrape-Zeitpunkt, teils veraltet); Fallback Jahr − Jahrgang |
| `pos` | häufigste Position (`tor`, `abwehr`, `mittelfeld`, `sturm`, `weitere`, …) |
| `role` | `starter`, wenn je in der Startelf, sonst `bench` |
| `nat`, `verband` | Nationalität, Landesverband-Kürzel |
| `cap` | je Kapitän (bool) |
| `min`, `matches`, `goals` | Summe Minuten, Anzahl Einsatzzeilen (auch 0-Minuten-Bank wie bisher), Tore – über alle gescrapten Bewerbe |
| `first`, `last` | ISO-Datum des ersten/letzten Einsatzes |
| `off`, `def`, `total`, `peak` | RAPM-Rating (Tore/90) oder `null` ohne Rating |
| `pct_talent`, `pct_total`, `pct_peak` | Perzentile aus `ratings.csv` (0 = bester) |
| `r_min`, `r_matches` | Minuten/Spiele laut Rating-Datei (Benchmark-Basis: `r_min ≥ 270`) |

Kategorie Jugend/Erwachsen eines Bewerbs wie bisher per `/\bU\s?\d|jugend/i`.

## matches_index.json

```json
{"v":1,"built":"…","teams":[...],"competitions":[...],
 "cols":["id","iso","date","time","comp","season","round","home","away","score","sh","sa","ht","venue","spect","ref","nev","coach_h","coach_a","url"],
 "rows":[["3839463","2025-08-03","03.08.2025","17:00",17,"2025/26","1. Runde",412,733,"1:3",1,3,"1:1",null,200,"Philip Gillesberger",14,"Marcel Thallinger","Andreas Wieland , MA","https://…"], ...]}
```
`comp`, `home`, `away` sind Indizes in `competitions`/`teams`. `nev` = Anzahl Events (wie bisher die
Spalte „Events“). Spielberichte ohne Datum und Teams (59 leere Seiten) sind nicht enthalten.
Sortiert nach Datum aufsteigend.

## /api/profile/{player_id}

```json
{"v":1,"built":"…",
 "player":{"id":"849039","name":"Sebastian Hölzl","birth_year":2001,"age":25,"nationality":"Deutschland",
           "verband":"S","club":"SV Grödig","foto_url":"https://…","youth":0,"first_match":"2012-…","last_match":"…",
           "n_clubs":4,"career":{"games":…,"goals":…,"minutes":…,"yellow":…,"yellowred":…,"red":…}},
 "rating":{"off":0.2004,"def":0.1993,"total":0.3997,"peak":0.3997,"pct_total":0.0,"pct_peak":0.0,"pct_talent":1.0,
           "minutes":5582,"matches":71,"teams":"FC Puch / SV Grödig","competitions":"Salzburger Liga"} | null,
 "bench":{"n":9076,"off":0.22,"def":0.07,"total":0.0,"peak":4.09} | null,   // Perzentil je Dimension (0 = bester), n = Spieler ≥ 270 Min.
 "games":[{"mid":"3405668","iso":"2023-08-05","date":"05.08.2023","season":"2023/24","comp":"Salzburger Liga","cat":"E",
           "team":"FC Puch","opp":"SK Adnet","ha":"H","score":"1:2","sf":1,"sg":2,"res":"N",
           "min":90,"on":0,"off":null,"goals":0,"gf":1,"ga":2,"pm":-1,"pos":"weitere","role":"starter"}, ...],
 "cohort":{"by":2001,"cat":"E","ok":true,"th":[…],"med":[…],"pct":5.63,"n":426},
 "split":{"n":503,"e_fewer":89.66,"e_zero":null,"j_fewer":0.0,"avg_games":34.83} | null,
 "clubs":[["SV Grödig",1720000000000,"at"], ...],              // [Verein, ab_ms, Land], wie bisher extras.v
 "achievements":[["2025/26","SV Grödig","KM","3. Platz in Salzburger Liga"], ...]}  // wie bisher extras.e
```

Semantik (identisch zur bisherigen Browser-Berechnung in `dashboard.html`):

* `games`: nur Einsätze mit `min > 0`, chronologisch (`iso` aufsteigend; Einsätze ohne Datum stehen
  vorne, `iso` = `""`). `cat` `"J"` = Jugend, `"E"` = Erwachsen. `off` = Auswechselminute oder `null`
  (= bis Schluss). `gf`/`ga`/`pm` = Tore für/gegen während der Einsatzzeit; **`pm = null`**, wenn die
  Tor-Timeline unvollständig ist (weniger Tor-Events mit Minute als der Spielstand verlangt) – solche
  Spiele zählen in keinem +/-, aber in Minuten/Toren. Nachspielzeit wie bisher: „90+2“ → 90.
* `cohort`: Referenz für den Chart „Plus-Minus akkumuliert“. `cat` = dominante Bewerbskategorie des
  Spielers (mehr Minuten; bei Gleichstand Erwachsen). `th[i]`/`med[i]` = Top-20-%-Schwelle (0,8-Quantil)
  und Median des kumulierten roh +/- pro 90 aller Jahrgangs-Spieler (nur `cat`-Bewerbe, ≥ 270 kumulierte
  Minuten) **zum Datum des i-ten Spiels in `vgames`** (= `games` mit `pm != null`, alle Kategorien);
  `null`, wenn < 20 Vergleichsspieler. `ok` = mindestens ein Datum mit ≥ 20 Vergleichsspielern. `pct` =
  Anteil (%) der Vergleichsspieler mit höherem Endwert als der Spieler (0 = bester), `n` = Anzahl
  Vergleichsspieler am letzten Spieltag. Der Spieler selbst gehört zur Kohorte.
* `split`: Minuten-Split-Vergleich (Karten „Minuten Nachwuchs/Erwachsene“, „Einsätze“) gegen alle
  Jahrgangs-Spieler mit Einsatz: `e_fewer` = % mit weniger Herren-Minuten (wenn Spieler > 0 Herren-Min.),
  sonst `e_zero` = % mit 0 Herren-Minuten; `j_fewer` = % mit weniger Jugend-Minuten; `avg_games` = Ø Einsätze.
  `null`, wenn < 20 Jahrgangs-Spieler oder kein Jahrgang.
* `bench`: Perzentile des Ratings unter allen `bench.n` Spielern mit ≥ 270 Rating-Minuten (wie `pctIn`).
* Saison-Tabelle, Karten-Summen, Running Average, kumulierte Spielerlinie, KI-Prompt: weiter im Browser aus
  `games` berechnen (billig, wenige Zeilen).

## /api/match/{match_id}

```json
{"match":{…alle Spalten von matches…},
 "lineup":{"home":[{"side":"home","role":"starter","number":"01","name":"…","player_id":"463666","captain":0,
                    "minutes":90,"on_min":0,"off_min":null,"goals":0,"position":"weitere","birth_year":1998}, …],
           "away":[…]},
 "events":[{"type":"goal","minute":"21","team":"away","player":"…","player_out":"","detail":"Strafstoß"}, …]}
```
`role` `starter`/`bench`, Reihenfolge wie im Spielbericht. Trainer stehen in `matches_index.json`
(`coach_h`/`coach_a`). Alter im Aufstellungsblock: aus `birth_year` (Jahr − Jahrgang) statt wie bisher
aus der CSV. `minute` ist der Rohtext (z. B. `"90+2"`, `"(Elfm.)"`), Anzeige wie bisher.

## Lokaler Testserver

```bash
./serve_local.sh [DATA_DIR] [PORT]      # Python 3.12 via uv, wie auf Render (Default: ./data, 8010)
```
`DATA_DIR` braucht `oefb.sqlite` (mit `dash_profile`, also nach `build_dashboard.py`) sowie
`scout.json(.gz)` und `matches_index.json(.gz)`.

## Leistungsziele

* Erstes sichtbares Scouting-Ergebnis < 1,5 s bei 10 Mbit/s (ein Request à 0,63 MB), Wiederbesuch per 304 sofort.
* Filter/Sortierung über 13 000 Zeilen < 50 ms; es werden nie alle 13 000 Zeilen als DOM gerendert.
* Profil öffnen < 300 ms (ein Request, 2–6 KB). Speicher im Browser < 100 MB (bisher > 500 MB).
