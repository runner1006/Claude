# OEFB Spielbericht-Scraper

Scrapt Spielberichte des ÖFB aus der Druckansicht:

```
https://www.oefb.at/Spiel/Druck/<SPIEL_ID>/
```

Beispiel-ID: `3855332`

## Installation

```bash
pip install -r requirements.txt
```

## Verwendung

```bash
# Einzelnes Spiel
python oefb_scraper.py --ids 3855332

# ID-Bereich (inklusive)
python oefb_scraper.py --id-range 3855330 3855340 --delay 1.5

# IDs aus Datei (eine pro Zeile, '#' = Kommentar)
python oefb_scraper.py --ids-file ids.txt --format both --out-dir ergebnisse

# Roh-HTML zur Selektor-Anpassung mitspeichern
python oefb_scraper.py --ids 3855332 --save-html
```

### Wichtige Optionen

| Option | Beschreibung | Default |
|--------|--------------|---------|
| `--ids ID [ID ...]` | Einzelne Spiel-IDs | – |
| `--id-range START END` | ID-Bereich (inklusive) | – |
| `--ids-file DATEI` | Datei mit IDs | – |
| `--out-dir` | Zielverzeichnis | `out` |
| `--format` | `json` \| `csv` \| `both` | `both` |
| `--save-html` | Roh-HTML je Spiel speichern | aus |
| `--delay` | Pause zwischen Anfragen (s) | `1.0` |
| `--retries` | Versuche pro Spiel | `4` |
| `--backoff` | Backoff-Basis (s, exponentiell) | `2.0` |

## Ausgabe

- **`matches.json`** – vollständige, verschachtelte Daten (Aufstellungen, Ereignisse etc.)
- **`matches.csv`** – eine Zeile pro Spiel (Grunddaten, Teams, Ergebnis, Trainer)
- **`events.csv`** – eine Zeile pro Ereignis (Tore, Karten, Wechsel)
- **`lineups.csv`** – eine Zeile pro Spieler

## ⚠️ Selektoren anpassen

Die CSS-Selektoren sind **heuristisch** gesetzt (label-basiert + Tabellen-Fallbacks),
weil das echte HTML der Seite beim Erstellen nicht abrufbar war. Vorgehen:

1. Einmal mit `--save-html` laufen lassen und `out/html/<id>.html` ansehen.
2. In `oefb_scraper.py` den Block `SELECTORS` mit den echten CSS-Selektoren füllen
   und bei Bedarf die Funktionen unter `# PARSER` feinjustieren.

Die spezifischen Selektoren greifen vor den Heuristiken – die Heuristiken bleiben
als Fallback aktiv.

## Hinweise

- Bitte fair scrapen: `--delay` nicht auf 0 setzen, Server nicht überlasten.
- `robots.txt` und Nutzungsbedingungen von oefb.at beachten.
- Nicht existierende IDs (HTTP 404) werden übersprungen und in der Ausgabe als
  `ok=false` markiert.
