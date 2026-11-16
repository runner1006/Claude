# Machbarkeitsprobe: ÖFB-Spieler mit Scoutastic verknüpfen

Stand 17.11.2026 · nur lesend · Skript `validierung/scoutastic_probe.py` · Rohergebnis
`validierung/scoutastic_probe_ergebnis.json`

## Ergebnis in fünf Sätzen

1. **Die Verknüpfung funktioniert: 34 von 35 Spielern eindeutig gefunden, kein mehrdeutiger
   Fall, einer fehlt in Scoutastic.**
2. Die API hat per GET **keine Namenssuche**. Der Weg führt über den Verein: Spielerliste des
   Stammvereins, sonst Abgänge des Vereins, dann Name plus Geburtsjahr.
3. **Unsere Datenbank kennt nur das Geburtsjahr.** Alle 13.523 Einträge in
   `players_profiles.json` lauten auf den 1. Jänner. Ein Abgleich über das exakte Geburtsdatum
   ist deshalb nicht möglich; Scoutastic liefert das echte Datum und kann es uns nachtragen.
4. Der Werdegang ist gut lesbar: Minuten je Saison und Bewerb sind bei allen 34 gefüllt, und
   jeder Bewerb trägt eine saubere Liga-Stufe (1. Liga, 2. Liga, 3. Liga …).
5. Der Vollabgleich für rund 5.200 Spieler kostet etwa 6.000 bis 7.000 Requests, also ein bis
   zwei Stunden Laufzeit. Der eigentliche Aufwand ist die Vereinszuordnung, nicht die API.

## 1. Stichprobe

| Gruppe | Regel | Anzahl |
|---|---|---:|
| Jugend | Bewerb mit „ÖFB Jugendliga" oder „Jugendregionalliga", Jahrgang 2005–2008, mindestens 1.800 Minuten, beste nach `pct_talent` | 20 |
| Erwachsene | Jahrgang 1998–2004, mindestens 3.000 Minuten, höchstes `total` | 10 |
| Schwierige Fälle | bewusst gewählt | 5 |

Die fünf schwierigen Fälle: Alexander Hofer (viermal in unserer Datenbank), Elias Neubauer
(dreimal), Felix Rudolf Wimmer (zweiter Vorname), Erik Baranyai-Ulvestad (Doppelname),
Loiange Delphin Ondoa Belinga (vierteiliger Name). Umlaute und weitere Doppelnamen kamen
schon in der Jugendgruppe vor: Überbacher, Stättner, Hüseyin Yücel, Lukasser-Weitlaner.

## 2. Suche und Trefferquote

### Was die API zur Suche anbietet

| Weg | Befund |
|---|---|
| `GET /players?search=…`, `name=`, `lastName=`, `yearOfBirth=` | wird still ignoriert (HTTP 200, ungefilterte Liste) |
| `GET /players/search?text=…` | HTTP 404 |
| `POST /players/search` mit `text`, `dateOfBirth`, `tolerance` | steht in der OpenAPI-Beschreibung, **nicht getestet**, weil die Probe nur GET erlaubt |
| `GET /players/team/{Stammverein}?includeClubTeams=true` | **funktioniert**: ein Request liefert alle aktuellen Spieler des Klubs samt Zweitteam, Akademie und Jugend, mit Geburtsdatum |
| `GET /players/transfers?from={Team-ID}&date={Unix-Sekunden}` | **funktioniert**: alle Abgänge eines Teams mit Spielername, Spieler-ID, Zielverein und Zielbewerb |
| `GET /players/debuts-by-competition?season=2025&competitionExternalId=A2` | **funktioniert**: alle Debütanten einer Liga und Saison als volle Spielerdokumente (2. Liga 2025/26: 180 Spieler in zwei Seiten, rund 10 Sekunden je Seite) |

### Der verwendete Ablauf

1. **ÖFB-Verein auf Scoutastic-Stammverein abbilden**, offline gegen die Teamliste der Instanz
   (115.667 Teams, liegt als Cache in `~/daten/scoutastic-probe/teams_all.json.gz`). Jedes
   Scoutastic-Team trägt `mainClubInternalId`, damit fallen „AKA FK Austria Wien U18",
   „Young Violets" und „FK Austria Wien" auf denselben Klub.
2. **Vereinsliste holen** (`/players/team/{id}?includeClubTeams=true`), zuerst für den
   aktuellen Profilverein, dann für die früheren Vereine.
3. **Treffer = Name passt und Geburtsjahr gleich.** Namen werden kleingeschrieben, Diakritika
   entfernt, Bindestriche zu Leerzeichen; Umlaute zusätzlich als ae/oe/ue versucht. Ein Teil
   des Nachnamens muss im Scoutastic-Nachnamen stehen, ein Vorname muss übereinstimmen.
4. **Nur wenn nichts gefunden:** Abgänge der Teams dieses Klubs seit 01.07.2022 nach dem Namen
   durchsuchen, dann das Spielerdokument holen und das Geburtsjahr prüfen.

### Wie ein Treffer aussieht

Elhadj Bah, ÖFB-ID 1078762, bei uns Jahrgang 2008, AKA FK Austria Wien U18:
Scoutastic `firstName` Elhadj, `lastName` Bah, `dateOfBirth` 2008-03-04, `teams` Young Violets
Austria Wien (Hauptteam) und AKA Austria Wien U18, dazu `transfermarktId` und `internalId`.
In derselben Vereinsliste steht sein Bruder Oumar Bah, Jahrgang 2010. **Der Nachname allein
hätte hier zwei Treffer ergeben, Vorname und Jahrgang trennen sie.**

### Trefferquote

| Gruppe | eindeutig | mehrdeutig | nicht gefunden |
|---|---:|---:|---:|
| Jugend (20) | 19 | 0 | 1 |
| Erwachsene (10) | 10 | 0 | 0 |
| Schwierige Fälle (5) | 5 | 0 | 0 |
| **Gesamt (35)** | **34** | **0** | **1** |

31 Treffer kamen aus der Vereinsliste, 3 aus den Abgängen (Jonas Überbacher: inzwischen
vereinslos; Milos Savic: Bosnien; Loiange Ondoa: Kosovo).

**Der eine Fehlende** ist Sebastian Hilpold (2008, AKA GAK 1902). Er ist kein Suchfehler: Die
Saisonkader 2025 von „AKA Grazer AK U18" und „U16" enthalten in Scoutastic je nur vier
Spieler. Scoutastic führt die ÖFB Jugendliga (zwölf Akademien) vollständig, die
Jugendregionalliga dagegen nur lückenhaft.

### Mehrdeutigkeit auflösen

In der Stichprobe war nie nötig, mehr als Name, Jahrgang und Verein zu verwenden. Für den
Vollabgleich in dieser Reihenfolge:

1. Geburtsjahr gleich (Pflicht).
2. Vereinsüberschneidung: Scoutastic-Verein oder ein Verein aus `performanceSummary` oder der
   Transferliste kommt in unserer Vereinshistorie vor.
3. Zeitliche Deckung: Saison und Bewerb in `performanceSummary` gegen unsere Einsätze
   (Scoutastic führt Regionalligen, Landesligen und ÖFB Jugendliga mit Minuten, die Zahlen
   lassen sich direkt nebeneinanderlegen).
4. Bleibt mehr als ein Kandidat, nicht zuordnen, sondern zur Handprüfung ausgeben.

In unserer Datenbank gibt es nur neun Paare mit gleichem Namen und gleichem Jahrgang.

## 3. Werdegang-Felder

Abruf: `GET /players/{internalId}?marketValues=true&performanceSummary=true&debuts=true`,
ein Request je Spieler. Transfers und Nationalteam brauchen je einen weiteren.

| Information | Feld | Füllung in der Stichprobe (34) | Urteil |
|---|---|---:|---|
| Aktueller Verein | `teams[]` mit `isMain` | 34 | zuverlässig, auch „Vereinslos" |
| Liga des aktuellen Vereins | Team → `league`, Stufe über `/competitions` | 32 | fehlt bei „Vereinslos" und einem Landesligisten ohne Ligaeintrag |
| **Minuten je Saison und Bewerb** | `performanceSummary[Saison][]`: `competitionId`, `contest`, `teamId`, `matchesPlayed`, `minutesPlayed`, `exchange`, `goals` | 34 | **das tragende Feld** |
| Liga-Stufe | `/competitions`: `level` 1–24, `levelDefinition`, `area`, `ageCategory` | alle 407 Saisonzeilen zugeordnet | sauber |
| Debüts | `debuts[]` mit Datum und Bewerb | 34 | zuverlässig, deckt sich mit den Minuten (17 von 17) |
| Transferhistorie | `/players/transfers/{id}`: Datum, von, nach, Zielbewerb, `isLoan`, `isIntern`, `fee` | 15 von 15 geprüften | zuverlässig, auch Akademie-Aufrückungen |
| Nationalteam | `/players/{id}/national-team-history`: Team, Debüt, Spiele, Tore | 3 von 15 geprüften | nur wer berufen wurde; plausibel |
| Marktwert | `marketValue`, `marketValueHistory` | 13 mit Wert über 0, 18 mit Verlauf | **nur für Profis**; 0 heißt „nicht bewertet" |
| Vertragsende | `contractExpires` | 10 | lückenhaft, nicht verwendet |
| Größe, Fuß | `height`, `foot` | 21, 17 | lückenhaft |
| Exaktes Geburtsdatum | `dateOfBirth` | 34 | zuverlässig, **fehlt uns** |

Aktualität: 29 der 34 Dokumente wurden im November 2026 zuletzt aktualisiert.

### Die Liga-Stufe

Ja, es gibt sie, und sie ist sauber. Österreich: `A1` Bundesliga = 1, `A2` 2. Liga = 2,
Regionalligen = 3, die neun Landesligen = 4, ÖFB Jugendliga = 7, ÖFB-Cup = 8, Nationalteams
= 11, Nachwuchs-Nationalteams = 17 und 20. Dieselbe Skala gilt für alle Länder.

**Drei Dinge, die die Stufe nicht sagt:**

- **Sie ist national.** Stufe 1 in Bosnien oder Stufe 2 in Zypern steht neben Stufe 1 in
  Österreich. Milos Savic hat 688 Minuten in der 2. Division Zyperns und 148 in Bosniens
  erster Liga. Für den Ländervergleich die Niveauskala aus `~/projekte/kontexttransfer` nehmen.
- **Zweitteams spielen in der 2. Liga.** Young Violets, Sturm II, Rapid II und Liefering zählen
  als Stufe 2. Das Skript markiert sie über `mainClubInternalId` als `zweitteam`.
- **Eine Saisonzeile ist kein Einsatz.** 11 der 46 Profiliga-Zeilen haben 0 Minuten: Der
  Spieler stand im Kader oder auf der Bank. Felix Wimmer (Ersatztormann SV Ried) hat zwei
  Bundesliga-Saisonen mit 0 Minuten. Immer `minutesPlayed` prüfen, nie das Vorhandensein.

## 4. Vorschlag: Was „Durchbruch" heißt

Allein aus `performanceSummary` und `/competitions`, in drei Stufen:

| Stufe | Regel | In der Stichprobe (34) |
|---|---|---:|
| **0 – kein Profi-Einsatz** | 0 Minuten in einer Erwachsenenliga der Stufe 1 oder 2 | 17 |
| **A – Profi-Debüt** | mindestens 1 Minute in Stufe 1 oder 2 (`ageCategory` Senior) | 13 |
| **B – Durchbruch** | **mindestens 900 Minuten in einer Saison** in Stufe 1 oder 2, **nicht im Zweitteam** | 4 |

Zusätzlich als eigene Marke **B2**: 900 Minuten in der 2. Liga nur im Zweitteam (in der
Stichprobe kein Fall, Tomy Baotic steht bei 532 Minuten für die Young Violets).

Begründung aus den Daten:

- **900 Minuten** sind zehn volle Spiele, rund ein Drittel einer Zweitliga-Saison. Die
  Schwelle trennt in der Stichprobe klar: Stammspieler (Scheucher 2.554, Buchegger 1.367,
  Savic 1.080, Glitia 1.020) von Einwechselspielern und Ersatztorleuten (1 bis 820 Minuten).
- **Minuten statt Kaderzugehörigkeit**, weil ein Drittel der Stufe-A-Fälle unter 50 Minuten
  liegt (Midzic 1 Minute Bundesliga, Reiterer 3, Bradaric 25).
- **Beste Saison statt Summe**, damit ein Spieler mit vier Saisonen à 200 Minuten nicht als
  Durchbruch zählt.
- **Die laufende Saison 2026/27 ist erst zu etwa einem Drittel gespielt.** Glitia und Savic
  haben ihre 1.000 Minuten in zwölf Runden erreicht; andere stehen bei 500 bis 800 und werden
  die Schwelle bis zum Sommer nehmen. Für die Validierung entweder nur abgeschlossene
  Saisonen werten oder die laufende auf Minutenanteil umrechnen.
- **Ausland:** nur Ligen zählen, die auf der Kontexttransfer-Skala mindestens das Niveau der
  österreichischen 2. Liga haben. Ohne diese Einschränkung zählt jede erste Liga der Welt.

Marktwert eignet sich als **zweite, unabhängige Marke** (etwa „Marktwert jemals mindestens
250.000 Euro"): Er ist bei allen vier Durchbruch-Fällen gefüllt mit einem Höchstwert von 250.000
bis 300.000 Euro, bei Amateuren steht 0. Als alleinige Definition taugt er nicht, weil 0 auch
„nie bewertet" heißt.

Wichtig für die Auswertung: Der Jahrgang 2008 ist heute 18. Für die Jugendgruppe misst die
Validierung derzeit den **Einstieg** in den Profifußball, noch nicht, ob sich jemand hält.

## 5. Vollabgleich: Aufwand und Grenzen

### Umfang

Jahrgänge 1998–2010 mit mindestens 900 Minuten: **5.230 Spieler** (ab 1.800 Minuten 3.621).
1.587 Spieler haben in unserer Datenbank kein Geburtsjahr und fallen für den Abgleich aus.

### Requests

| Schritt | Requests |
|---|---:|
| Bewerbe (`/competitions`) | 3 |
| Vereinslisten für rund 300 Stammvereine | 300 |
| Abgänge für rund 600 Teams (Kampfmannschaft, Zweitteam, U18, U16) | 600 |
| Debütanten Bundesliga und 2. Liga, vier Saisonen | 20 |
| Spielerdokument je Treffer | bis 5.200 |
| Transfers und Nationalteam, nur für Stufe A und B (geschätzt 15 %) | 1.600 |
| **Summe** | **rund 6.000 bis 7.700** |

In der Probe: Suche im Mittel 1,2 Requests je Spieler (0 bis 6, weil sich Spieler desselben
Klubs eine Vereinsliste teilen), Werdegang 1 bis 3. Die ganze Probe hat 123 Requests
gebraucht, bei leerem Cache wären es 111 für den Lauf selbst.

### Geschwindigkeit und Limit

- Antwortzeit 0,3 bis 0,6 Sekunden; die Debütantenliste 10 Sekunden.
- Antwortheader `X-RateLimit-Limit: 1000`, nach fünf Requests `Remaining: 995`. Das Fenster
  ist kurz (die 107 Requests wenige Minuten davor waren schon nicht mehr angerechnet), seine
  genaue Länge ist nicht bestimmt. Mit 0,35 Sekunden Pause blieb die Probe weit darunter.
- Bei einem Request alle 0,7 Sekunden dauert der Vollabgleich **rund eineinhalb Stunden**,
  einmalig. Jede Antwort wird als gzip abgelegt, ein zweiter Lauf kostet nichts.

### Fehlerquellen, nach Gewicht

1. **Vereinszuordnung.** Die automatische Zuordnung über den Namen trifft nur 232 von 437
   unserer Teamnamen (Sponsorennamen wie „RZ Pellets WAC", „SC EGLO Schwaz", Kurzformen wie
   „Vienna", Spielgemeinschaften). Für die Stichprobe waren 39 Handkorrekturen nötig. Besser:
   je Bewerb und Saison die Teamliste aus Scoutastic holen (`/competitions/{id}/teams/{Saison}`,
   getestet) und nur innerhalb der 12 bis 16 Teams zuordnen.
2. **Nur Geburtsjahr auf unserer Seite.** Name plus Jahr plus Verein hat in der Stichprobe
   gereicht. Bei häufigen Namen ohne Vereinsüberschneidung bleibt es unsicher.
3. **Lücken in Scoutastic.** Jugendregionalliga-Akademien sind dünn besetzt (GAK U18: vier
   Spieler). Wer dort fehlt und nie Profi wurde, ist kein Problem für die Validierung, er zählt
   als „kein Durchbruch". Kritisch wäre nur ein fehlender Profi, und Profis sind vollständig.
4. **Abgewanderte Spieler** stehen nicht mehr in der Vereinsliste. Der Weg über die Abgänge
   hat alle drei Fälle gefunden, kostet aber 4 bis 6 Requests je Spieler.
5. **Namensformen.** Scoutastic kürzt: „Felix Wimmer" statt „Felix Rudolf Wimmer", „Loiange
   Ondoa" statt „Loiange Delphin Ondoa Belinga". Deshalb reicht ein gemeinsamer Vorname und ein
   gemeinsamer Nachnamensteil. Geschwister im selben Klub trennt nur Vorname plus Jahrgang.
6. **Saisonlabel.** `season` ist das Startjahr. Bei Kalenderjahr-Ligen (Skandinavien, Irland)
   ist das Label um ein Jahr versetzt.
7. **Unser eigenes Profil ist teils veraltet.** Bei Ondoa Belinga nennt das ÖFB-Profil noch
   „ADMIRAL Bundesliga" bei der SV Ried; laut Scoutastic wechselte er im August 2026 in den
   Kosovo und hat keine Bundesliga-Minute.

### Empfehlung für den Vollabgleich

**Den Pool einmal ernten, dann offline abgleichen** statt je Spieler zu suchen:

1. Für alle Bewerbe, die wir führen, und die beiden Profiligen die Teamlisten je Saison holen.
2. Je Stammverein die Vereinsliste und je Team die Abgänge seit 2022 holen.
3. Daraus eine lokale Tabelle „Scoutastic-Spieler mit Österreich-Bezug" bauen und gegen unsere
   Datenbank über Name, Jahrgang und Vereinsüberschneidung abgleichen.
4. Nur für die Treffer das Spielerdokument holen.

Die Debütantenlisten der Bundesliga und 2. Liga dienen als **Gegenprobe von der Zielseite**:
Jeder österreichische Debütant, der in unserer Datenbank vorkommt, muss im Abgleich als
Stufe A oder B auftauchen. Fehlt einer, ist die Zuordnung dort gerissen.

## Offene Punkte

- **`POST /players/search`** wäre vermutlich der kürzeste Weg (Name plus Geburtsdatum mit
  Toleranz). Er liest nur, ist aber ein POST und widerspricht der Regel „nur GET" im
  Scoutastic-Skill. Entscheidung nötig, ob ein lesender POST erlaubt ist.
- **Länge des Rate-Limit-Fensters** vor dem Vollabgleich bestimmen (Header `X-RateLimit-Reset`
  über mehrere Minuten beobachten).
- **Exakte Geburtsdaten zurückspielen:** Nach dem Abgleich kann `dateOfBirth` aus Scoutastic
  unsere Platzhalter „01.01." ersetzen, wo ein Treffer vorliegt.
- **Auslandsniveau:** Liste der Ligen festlegen, die als Durchbruch zählen.
- **Zweitteams:** entscheiden, ob 900 Minuten für Young Violets, Sturm II oder Liefering als
  Durchbruch oder als eigene Vorstufe gelten.

## Dateien und Datenschutz

- `validierung/scoutastic_probe.py`: Probe-Skript. Token nur aus `SCOUTASTIC_API_TOKEN`, der
  Datei aus `SCOUTASTIC_ENV` oder `~/zugaenge/scoutastic.env`. Ausschließlich GET, Budget
  über `SCOUTASTIC_MAX_REQUESTS` (Vorgabe 150), `--offline` rechnet nur aus dem Cache.
- `validierung/scoutastic_probe_ergebnis.json`: je Spieler Status, Methode, IDs,
  Geburtsdatum, aktuelle Teams, Saisonzeilen mit Stufe, Debüts, Marktwert, Durchbruch-Stufe.
  **Keine Vertragsenden, keine Berater, keine Gehälter** (nur die Angabe, ob das Feld gefüllt ist).
- Rohantworten der API liegen außerhalb des Repos in
  `~/daten/scoutastic-probe/oefb_validierung/` (120 gzip-Dateien). Sie enthalten die vollen
  Spielerdokumente samt Vertragsfeldern und gehören nicht ins Repo.
