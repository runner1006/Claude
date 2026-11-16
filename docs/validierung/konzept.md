# Validierung der Ratings: Erkennt das Modell spätere Aufsteiger?

Stand 17.11.2026. Dieses Papier beschreibt die Methodik, den ersten Pilot auf eigenen Daten und den Plan für
den Abgleich mit Scoutastic.

## 1. Die Frage

Ein Klub will wissen: Wenn das Dashboard einen Spieler in den Top 2 % seines Jahrgangs zeigt, wie oft wird aus
so einem Spieler später wirklich etwas? Das Paper von Hvattum nennt „Top 20 % erfassen rund 80 % der später
wertvollsten Spieler“. Diese Zahl stammt nicht aus unseren Daten und beantwortet eine andere Frage. Wir
unterscheiden deshalb zwei Kennzahlen:

| Kennzahl | Frage | Beispiel |
|---|---|---|
| **Trefferquote** | Von 100 Spielern mit dieser Einstufung: Wie viele schaffen es? | „57 von 100“ |
| **Erfassungsquote** | Von 100 späteren Aufsteigern: Wie viele hatten wir oben? | „57 % waren in den Top 20 %“ |

Für Scouts zählt vor allem die Trefferquote, immer im Vergleich zur **Basisquote** (wie viele schaffen es
ohne jede Auswahl).

## 2. Methodik

**Kein Blick in die Zukunft.** Das heutige Rating nutzt alle Saisonen ab 2023/24. Für einen Rückblick dürfen
wir nur verwenden, was man damals wusste. Ablauf:

1. **Lernzeitraum festlegen**, zum Beispiel nur die Saison 2023/24. Die Ratings werden mit `plusminus.py`
   ausschließlich aus diesen Spielen neu gerechnet.
2. **Spieler einstufen** nach diesem frühen Rating: Talent-Rang im Jahrgang (Nachwuchs) bzw. Gesamt-Rating
   (Erwachsene).
3. **Ergebnis später messen**, frühestens eine Saison nach Ende des Lernzeitraums.
4. **Quoten je Einstufung** berechnen und mit der Basisquote vergleichen. Zusätzlich die Top 10, 20 und 30
   namentlich durchgehen.

**Definition „Durchbruch“** (Stufen, damit das Ergebnis nicht an einer einzigen Schwelle hängt):

| Stufe | Definition | Quelle |
|---|---|---|
| A Profi | Kader/Einsätze in Bundesliga oder 2. Liga, vergleichbare Auslandsliga | ÖFB-Profil (aktueller Bewerb), Scoutastic |
| B Stamm Regionalliga | mindestens 900 Minuten je Saison in der Regionalliga | eigene Daten |
| C Stamm Erwachsene | zusätzlich mindestens 1.800 Minuten Landesliga/Oberliga | eigene Daten |

**Bekannte Grenzen**
- Wir haben erst vier Saisonen. Der längste mögliche Rückblick ist 2023/24 nach 2026/27.
- Die Stichprobe enthält nur Spieler mit genug Minuten im Lernzeitraum. Wer damals kaum spielte, fehlt.
- Profiligen und Ausland sind nicht in unseren Daten. Spieler, die dorthin wechseln, verschwinden bei uns.
  Das ÖFB-Profil zeigt nur den aktuellen Bewerb zum Zeitpunkt des Abrufs und keine Auslandsstationen.
  Genau hier brauchen wir Scoutastic.
- Akademiespieler haben strukturell bessere Chancen. Ein Teil der Trefferquote ist „Akademie“, nicht „Rating“.
  Das lässt sich trennen, indem man innerhalb derselben Akademie vergleicht.

## 3. Pilot auf eigenen Daten (erledigt)

Skript: `validierung/rueckblick_pilot.py`, Ergebnis: `validierung/rueckblick_pilot_ergebnis.json`.
Lernzeitraum 2023/24 (3.388 Spiele), Ergebniszeitraum ab 2025/26, Profi-Status aus dem ÖFB-Profil.

**Nachwuchs:** 544 Spieler der Jahrgänge 2005 bis 2008 mit mindestens 900 Jugend-Minuten in 2023/24.
Durchbruch = Stufe A oder B. Basisquote 26 %.

| Einstufung 2023/24 | Spieler | Durchbruch | Trefferquote | Erfassungsquote |
|---|---|---|---|---|
| Top 2 % | 28 | 16 | 57 % | 11 % |
| Top 10 % | 140 | 54 | 39 % | 38 % |
| Top 20 % | 245 | 81 | 33 % | 57 % |
| 20 bis 50 % | 197 | 45 | 23 % | 32 % |
| untere Hälfte | 102 | 15 | 15 % | 11 % |

Die namentliche Probe: Von den besten 10 nach damaligem Talent-Rang spielen heute 7 in Bundesliga oder 2. Liga,
9 haben Stufe A oder B erreicht. Top 20: 12 Profis, 14 Durchbrüche. Top 30: 14 Profis, 17 Durchbrüche.

Lesart: Das Rating trennt klar. Die Top 2 % schaffen es gut doppelt so oft wie der Schnitt und fast viermal so
oft wie die untere Hälfte. Die Erfassungsquote der Top 20 % liegt bei uns bei 57 %, nicht bei 80 %.

**Erwachsene:** 336 Spieler bis 23 Jahre mit mindestens 1.800 Minuten in 2023/24, Ergebnis = heute Profi.
Basisquote 6,5 %, Top 20 % nach Gesamt-Rating 8,8 %. Das Signal ist schwach und die Fallzahl klein (22 Treffer).
Mögliche Gründe: Aufstieg aus der Regionalliga in den Profifußball ist selten und hängt stark vom Alter ab,
und eine einzige Saison ist für ein belastbares Erwachsenen-Rating knapp. Hier ist der Abgleich mit Scoutastic
am wichtigsten, weil Wechsel ins Ausland und in höhere Ligen sonst fehlen.

**Vorbehalte zum Pilot**
- Mehrere Spieler aus den Top 30 stehen als „kein Durchbruch“ da, obwohl sie vermutlich bei einem Profiklub
  oder im Ausland sind (0 Minuten in allen unseren Ligen). Die wahren Quoten liegen eher höher.
- Der Talent-Rang wird im ganzen Jahrgang gebildet, die Stichprobe verlangt aber 900 Minuten. Deshalb liegen
  245 von 544 Spielern in den „Top 20 %“.

## 4. Abgleich mit Scoutastic

Die technische Probe ist erledigt: `docs/validierung/scoutastic-probe.md`, Skript `validierung/scoutastic_probe.py`
(nur lesende GET-Aufrufe), Ergebnis `validierung/scoutastic_probe_ergebnis.json`.

**Ergebnis der Probe (35 Spieler, 123 Requests)**

| Gruppe | eindeutig gefunden | nicht gefunden |
|---|---|---|
| Nachwuchs (20) | 19 | 1 |
| Erwachsene (10) | 10 | 0 |
| schwierige Namen (5) | 5 | 0 |

- **Matching-Weg:** ÖFB-Verein auf den Scoutastic-Stammverein abbilden, dessen Kader mit Zweitteam und Akademie
  in einem Request laden, dann Name plus Geburtsjahr vergleichen. Für Abgänge die Transferliste des Vereins.
  Eine Namenssuche per GET gibt es nicht.
- **Unsere Geburtsdaten taugen nicht zum Abgleich:** In `players_profiles.json` steht bei allen Spielern der
  1. Jänner, wir kennen also nur das Geburtsjahr. Scoutastic hat das echte Datum und kann es nachliefern.
- **Werdegang:** Minuten je Saison und Bewerb sind bei allen gefundenen Spielern gefüllt, die Liga-Stufe ist
  sauber vorhanden (Bundesliga 1, 2. Liga 2, Regionalliga 3). Marktwert nur bei Profis, Vertragsende lückenhaft.
- **Lücke:** Die ÖFB Jugendliga ist in Scoutastic vollständig, die Jugendregionalliga nur dünn.
- **ÖFB-Profile sind teils veraltet:** Ein Spieler steht bei uns noch als Bundesliga-Spieler, ist laut
  Scoutastic aber im Sommer 2026 ins Ausland gewechselt und hat keine Bundesliga-Minute. Der Profi-Status im
  Pilot aus Abschnitt 3 enthält also Fehler in beide Richtungen.

**Durchbruch-Definition mit Scoutastic** (ersetzt Stufe A aus Abschnitt 2):

| Stufe | Regel |
|---|---|
| Profi-Debüt | mindestens 1 Minute in einer Liga der Stufe 1 oder 2 |
| Durchbruch | mindestens 900 Minuten in einer Saison in Stufe 1 oder 2, nicht im Zweitteam |

In der Probe trennen 900 Minuten klar Stammspieler von Einwechselspielern.

**Offene Entscheidungen**
- Zählen 900 Minuten für ein Zweitteam in der 2. Liga (Young Violets, Sturm II, Liefering) als Durchbruch
  oder als eigene Vorstufe?
- Welche Auslandsligen zählen? Vorschlag: ab dem Niveau der österreichischen 2. Liga nach der Skala aus dem
  Kontexttransfer-Modell.
- Darf die Suche per `POST /players/search` genutzt werden? Sie wäre der kürzeste Weg, ist technisch aber ein
  POST und im Scoutastic-Skill bisher ausgeschlossen.

**Nächste Schritte, bewusst klein**

1. **Pilot 1, Nachwuchs:** die Top 30 je Jahrgang 2005 bis 2008 aus dem Rückblick plus 30 zufällige
   Vergleichsspieler je Jahrgang, rund 240 Spieler. Frage: Wie viele „kein Durchbruch“ sind in Wahrheit Profis?
2. **Pilot 2, Erwachsene:** die Top 30 nach Gesamt-Rating 2023/24 und 30 Vergleichsspieler.
3. **Frühere Akademie-Jahrgänge:** Für Spieler vor 2023/24 haben wir kein Rating. Scoutastic liefert hier die
   Basisquote je Akademie („Wie viele schaffen es überhaupt?“), über die Debütantenlisten von Bundesliga und
   2. Liga. Das ist ein eigener, kleiner Baustein.
4. **Vollabgleich** erst danach: rund 5.200 Spieler, 6.000 bis 7.700 Requests, einmalig etwa eineinhalb
   Stunden. Größter Aufwand ist die Zuordnung der Vereinsnamen (nur 232 von 437 treffen automatisch).

## 5. Was davon schon im Dashboard steht

Die Profilseite V2 zeigt bei Spielern bis 19 Jahre die Trefferquote aus dem Pilot als Satz („57 von 100 haben
den Sprung geschafft, im Schnitt 26 von 100“), mit dem Hinweis „erste Auswertung“. Die Werte stehen in
`TALENT_CHECK` in `dashboard.html` und müssen nach jedem neuen Rückblick aktualisiert werden.
