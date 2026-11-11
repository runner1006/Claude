---
title: Mannschaftsstärke, Ergebniswahrscheinlichkeiten und Trainerwirkung aus ÖFB-Ergebnisdaten
subtitle: Methodische Erweiterung des Plus-Minus-Modells um Team-Elo, Punkte-Plus-Minus und ein Trainermodul – Stand der Forschung, Methodik, Mehrwerte und Umsetzungsplan
autor: Strykerlabs Analytics
datum: 11.11.2026
status: Konzept 1.0 – Umsetzung noch nicht begonnen; baut auf plusminus.py (Stand Commit 7a7b2cf) auf
---

# Mannschaftsstärke, Ergebniswahrscheinlichkeiten und Trainerwirkung aus ÖFB-Ergebnisdaten

## 1. Zusammenfassung

Das bestehende Modell schätzt für rund 13 600 Spieler aus 29 ÖFB-Bewerben ein Plus-Minus-Rating: Wie viele Tore pro 90 Minuten ein Spieler zum Torverhältnis seiner Mannschaft beiträgt, bereinigt um Mit- und Gegenspieler, Heimvorteil und Über- oder Unterzahl. Es beantwortet die Frage nach dem *Spieler*. Es beantwortet nicht, wie stark eine *Mannschaft* ist, mit welcher Wahrscheinlichkeit sie ein Spiel gewinnt, welche Spieler nicht nur Tore, sondern *Punkte* bewegen, und welchen Anteil der *Trainer* hat.

Dieses Dokument beschreibt eine Erweiterung in fünf Bausteinen, die allein mit den vorhandenen Ergebnis-, Aufstellungs- und Trainerdaten auskommt, also ohne Wettquoten und ohne xG:

| Baustein | Inhalt | Ergebnis |
|---|---|---|
| M1 Team-Elo | dynamisches Stärkerating je Mannschaft aus Ergebnissen, mit Tordifferenz, Heimvorteil und Saisonübergang | Stärke jeder Mannschaft an jedem Spieltag |
| M2 Ergebniswahrscheinlichkeiten | geordnetes Logit-Modell und Poisson-Tormodell auf der Elo-Differenz | P(Sieg), P(Remis), P(Niederlage) und erwartete Punkte je Spiel |
| M3 Kaderstärke und Kombination | Summe der Plus-Minus-Ratings der Startelf als zweite Stärkegröße; Kombination mit Elo | aufstellungsabhängige Prognose; Zerlegung Teamstärke = Kader + Mannschaftsmehrwert |
| M4 Punkte-Plus-Minus | dieselbe Regression wie heute, aber mit der Veränderung der erwarteten Punkte statt Toren als Zielgröße | Rating „Punkte pro 90“: wer Spiele entscheidet, nicht nur Tore erzielt |
| M5 Trainermodul | Amtszeiten, Punkte über Erwartung, Mannschaftsmehrwert und Spielerentwicklung je Amtszeit, mit Reliabilitätsprüfung | erste objektive Trainerbewertung im Amateur- und Jugendbereich |

Der zentrale methodische Punkt ist ein scheinbarer Widerspruch: Das Plus-Minus-Modell rechnet die Mannschaftsstärke bewusst heraus, ein Elo-Rating misst genau sie. Kapitel 5 zeigt, warum Elo deshalb *nicht* als Erklärgröße in die Spieler-Regression gehört, und welche drei Wege den Widerspruch auflösen. Kapitel 9 beschreibt die Mehrwerte, Kapitel 11 einen Umsetzungsplan in acht Phasen mit Abnahmekriterien. Umgesetzt ist davon noch nichts.

Zwei Befunde aus dem Datenbestand prägen die Methodik (Kapitel 2.3): Über Mannschaften allein zerfallen die 29 Bewerbe in fünf voneinander getrennte Gruppen, über Spieler bilden sie eine einzige. Und die Trainerdaten sind fast vollständig (99,6 % der Spiele), enthalten aber viele Einzelspiel-Vertretungen, die vor jeder Trainerauswertung bereinigt werden müssen.

## 2. Ausgangslage: das bestehende Modell

### 2.1 Datenbestand (Stand 07.11.2026)

| Größe | Wert |
|---|---|
| Spiele | 12 883, davon 12 824 mit Endstand |
| Saisonen | 2023/24, 2024/25, 2025/26, 2026/27 (laufend, 1 893 Spiele) |
| Bewerbe | 29: Regionalligen, Landesligen und Oberligen aller Bundesländer, ÖFB-Jugendliga und Jugendregionalligen U15, U16, U18 |
| Mannschaften | 450, davon 382 mit mindestens 20 Spielen |
| Spieler mit Rating | 13 629, davon 4 919 mit Einsätzen in mehr als einem Bewerb |
| Segmente konstanter Aufstellung | 77 283, Ø 15 Minuten, 46 408 Tore |
| Trainer je Spiel | Heim 12 831, Gast 12 819 von 12 883 Spielen erfasst |

Ergebnisverteilung, die jedes Modell reproduzieren muss:

| Kategorie | Spiele | Heimsieg | Remis | Auswärtssieg | Tore je Spiel |
|---|---|---|---|---|---|
| Erwachsene | 10 394 | 46,5 % | 20,8 % | 32,7 % | 3,41 |
| Jugend | 2 430 | 45,7 % | 16,8 % | 37,5 % | 4,11 |
| gesamt | 12 824 | 46,4 % | 20,0 % | 33,6 % | 3,55 |

Wer jedem Spiel einfach diese Häufigkeiten als Prognose gibt, erreicht einen Ranked Probability Score (RPS, Kapitel 6.2) von **0,236**. Das ist die Untergrenze, die jedes Stärkemodell deutlich unterbieten muss.

### 2.2 Methodik des Plus-Minus-Ratings

Die Methodik folgt Hvattum (2020) und Hvattum, Kriegl und Čulík (2023); einen Überblick über die Modellfamilie gibt Hvattum (2019).

**Segmente.** Jedes Spiel wird an jeder Ein- und Auswechslung und jeder Roten Karte in Segmente mit unveränderter Aufstellung geschnitten. Jedes Segment liefert zwei Beobachtungen, einmal mit der Heim-, einmal mit der Gastmannschaft im Angriff (Ilardi 2007).

**Modell.** Für die Heimtore in Segment s mit Dauer d gilt näherungsweise

```
g_H(s) ≈ d/90 · ( c + h + Σ_{i ∈ Heim} β_i^O − Σ_{j ∈ Gast} β_j^D + μ · (n_H − n_A) )
```

und symmetrisch für die Gasttore ohne Heimvorteil h. β^O und β^D sind Offensiv- und Defensivrating je Spieler in Toren pro 90 Minuten, c die Grundtorrate, μ der Effekt eines Mannes mehr am Feld.

**Schätzung.** Gewichtete Kleinste-Quadrate mit Ridge-Strafterm:

```
β̂ = argmin_β  Σ_r w_r · (y_r − x_r β)²  +  λ · Σ_k β_k²
```

λ wird per Kreuzvalidierung über Spiele gewählt (aktuell λ = 30). Das Total-Rating ist β^O + β^D, das Peak-Rating addiert einen Alterszuschlag nach einer festen Alterskurve, das Talent-Perzentil rankt je Geburtsjahrgang nach Peak-Rating und Minuten.

**Zeitgewichtete Variante (seit 07.11.2026).** Eine zweite Schätzung mit w = exp(−ln 2 · Alter in Tagen / 365) liefert „Total akt.“: Die laufende Saison zählt voll, die Vorsaison halb. Beide Varianten korrelieren mit r = 0,90.

**Kenngrößen des aktuellen Laufs.** Heimvorteil +0,305 Tore pro 90 Minuten, Überzahl +0,626 Tore pro 90 Minuten je Spieler, eine einzige zusammenhängende Spielerkomponente.

### 2.3 Zwei Befunde zur Struktur der Daten

**Ligen sind über Mannschaften kaum, über Spieler vollständig verbunden.** Verbindet man zwei Bewerbe, sobald eine Mannschaft in beiden gespielt hat (Auf- und Abstieg), entstehen fünf getrennte Gruppen:

| Gruppe | Bewerbe |
|---|---|
| West, Mitte, Süd | 16: Regionalligen Mitte, West, Nord, Süd; Landes- und Oberligen von Tirol, Vorarlberg, Salzburg, Oberösterreich, Kärnten, Steiermark |
| Ost | 5: Regionalliga Ost, Wiener Stadtliga, 1. Landesliga Niederösterreich, Burgenlandliga, Landesliga Burgenland |
| U18 | 3: Jugendliga, Jugendregionalliga, Jugendregionalliga Ost |
| U16 | 3: analog |
| U15 | 1: Jugendliga U15 |

Verbindet man Bewerbe dagegen über Spieler mit Einsätzen in beiden, gibt es 279 verbundene Bewerbspaare und eine einzige Gruppe. Folge: Ein reines Ergebnis-Elo kann die Stärke einer Ost-Mannschaft nicht mit der einer West-Mannschaft vergleichen, und eine U18 nicht mit einer Landesliga. Das Plus-Minus-Modell kann es. Daraus folgt die Rolle der Spieler-Ratings als Brücke zwischen den Ligen (Kapitel 6.1, Schritt 4).

**Trainerdaten sind vollständig, aber verrauscht.** Die Spielberichte nennen 1 052 verschiedene Trainer. Ordnet man je Mannschaft die Spiele nach Datum, ergeben sich 1 986 Folgen desselben Trainers. Davon dauern 536 nur ein Spiel, und 421 folgen dem Muster A–B–A mit einem B von höchstens zwei Spielen: Vertretungen, keine Trainerwechsel. Nach Bereinigung bleiben 349 Amtszeiten mit mindestens 20 Spielen bei Erwachsenen und 118 in der Jugend. 136 Trainer haben bei mindestens zwei Klubs je mindestens zehn Spiele betreut; sie erlauben die Prüfung, ob ein Trainereffekt mit dem Trainer wandert.

### 2.4 Grenzen des bestehenden Modells

1. **Kein Mannschaftsmaß.** Das Modell liefert keine Stärke je Mannschaft und keine Wahrscheinlichkeit für ein Spielergebnis. Im Strykerlabs-Gesamtbild (Projekt-Onepager) ist der Kontextring „Mannschaft“ deshalb als offen markiert.
2. **Jedes Tor zählt gleich.** Das 1:0 in der 85. Minute und das 6:0 in der 85. Minute wiegen gleich viel. Ein Spieler, der vor allem in entschiedenen Spielen trifft, wird überschätzt.
3. **Trainer sind unsichtbar.** Was eine Mannschaft über die Summe ihrer Spieler hinaus leistet, verteilt das Modell auf die Spieler dieser Mannschaft, weil es keinen Teamterm hat.
4. **Keine Validierung am Ergebnis.** Ob die Ratings künftige Ergebnisse vorhersagen, ist bisher nicht geprüft. Die Kreuzvalidierung bewertet Tore je Segment, nicht Ausgänge von Spielen.

## 3. Fragestellung

| Nr. | Forschungsfrage |
|---|---|
| F1 | Wie gut lassen sich Ausgänge von Amateur- und Jugendspielen allein aus vergangenen Ergebnissen vorhersagen, gemessen an RPS und Kalibrierung? |
| F2 | Verbessert die Kaderstärke der tatsächlichen Startelf, gemessen mit den Plus-Minus-Ratings, die Prognose über ein Team-Elo hinaus? |
| F3 | Welche Spieler erhöhen die Gewinnwahrscheinlichkeit ihrer Mannschaft, und wie unterscheidet sich diese Rangliste von der Torrangliste? |
| F4 | Gibt es einen messbaren, über Amtszeiten und Klubs stabilen Trainereffekt auf Punkte über Erwartung, auf den Mannschaftsmehrwert über die Kaderstärke hinaus und auf die Entwicklung der Spieler? |

## 4. Stand der Forschung

### 4.1 Mannschaftsstärke aus Ergebnissen

**Elo-Ratings.** Das Elo-System aktualisiert nach jedem Spiel die Stärke beider Mannschaften um die Differenz aus tatsächlichem und erwartetem Ergebnis. Hvattum und Arntzen (2010) übertragen es auf den Fußball, auch in einer Variante, die die Tordifferenz berücksichtigt, und leiten aus der Elo-Differenz über eine geordnete Logit-Regression Wahrscheinlichkeiten für Heimsieg, Remis und Auswärtssieg ab. Die Elo-Modelle schlugen vier von sechs Vergleichsmethoden, blieben aber hinter Wettquoten zurück. Lasek, Szlávik und Bhulai (2013) vergleichen Rankingsysteme für Nationalmannschaften; eine Elo-Variante sagt am besten vorher und deutlich besser als die offizielle FIFA-Rangliste.

**Tormodelle.** Maher (1982) modelliert die Tore beider Mannschaften als Poisson-verteilt mit Angriffs- und Abwehrstärke je Mannschaft. Dixon und Coles (1997) korrigieren die Häufigkeit torarmer Ergebnisse und gewichten ältere Spiele exponentiell geringer; ihr Modell ist bis heute die Referenz. Ley, Van de Wiele und Van Eetvelde (2019) vergleichen zehn solcher Stärkemodelle mit Zeitgewichtung über eine Halbwertszeit und finden, dass das bivariate Poisson-Modell am besten vorhersagt.

**Pi-Ratings.** Constantinou und Fenton (2013) führen ein Rating mit getrennter Heim- und Auswärtsstärke ein, das auf Tordifferenzen reagiert, dabei aber große Siege dämpft. Auf fünf Premier-League-Saisonen übertrifft es Elo.

**Prognose nur aus Ergebnissen.** Die 2017 Soccer Prediction Challenge (Dubitzky et al. 2019) stellte genau die Aufgabe dieses Projekts: Ausgänge aus einer Datenbank von 216 743 Ligaspielen aus 52 Ligen vorherzusagen, die nur Datum, Mannschaften und Endstand enthält. Die Beiträge zeigen, dass Rating-Merkmale wie Elo und Pi-Rating den Kern guter Modelle bilden.

### 4.2 Wahrscheinlichkeiten und ihre Bewertung

**Remis.** Davidson (1970) erweitert das Bradley-Terry-Paarvergleichsmodell um einen Remis-Parameter; das Remis wird umso wahrscheinlicher, je ähnlicher beide Stärken sind. Das ist die Alternative zum geordneten Logit.

**Bewertung.** Fußballausgänge sind geordnet: Ein Remis liegt näher am Sieg als die Niederlage. Constantinou und Fenton (2012) begründen deshalb den Ranked Probability Score (Epstein 1969) als Standardmaß. Wheatcroft (2021) hält dagegen, dass der logarithmische Score („Ignorance“) besser trennt. Beide Maße sind auszuweisen.

### 4.3 Wettquoten als Maßstab

Wettquoten enthalten mehr Information als jedes öffentliche Ergebnismodell. Štrumbelj (2014) zeigt, wie man aus Quoten Wahrscheinlichkeiten gewinnt, und dass die Methode von Shin genauer ist als die einfache Normierung der Kehrwerte. Wunderlich und Memmert (2018) bauen ein Elo-Rating, das statt Ergebnissen Quoten verarbeitet, und schlagen damit klassische Elo-Modelle. Für das ÖFB-Unterhaus und die Jugend gibt es keine flächendeckenden Quoten. Quoten sind hier deshalb Prüfstein für eine Stichprobe, nicht Eingangsgröße.

### 4.4 Verbindung von Mannschafts- und Spielerratings

**Die direkte Vorlage.** Arntzen und Hvattum (2021) prognostizieren Spielausgänge mit zwei Größen: der Elo-Differenz der Mannschaften vor dem Spiel und der mittleren Differenz der Plus-Minus-Ratings der beiden Startelfen. Team- und Spielerratings prognostizieren je für sich etwa gleich gut. **Beide zusammen sind signifikant besser als jede allein.** Das ist der empirische Kern von Baustein M3 und stammt aus derselben Forschungsgruppe wie die Methodik des bestehenden Modells.

**Punkte statt Tore.** Kharrat, McHale und López Peña (2020) passen Plus-Minus an den Fußball an und schlagen eine Variante vor, deren Zielgröße die Veränderung der erwarteten Punkte ist, berechnet aus Wahrscheinlichkeiten während des Spiels. Hvattum (2020) ordnet das als eines von drei möglichen Zielmaßen ein: Tore, xG und Veränderung der erwarteten Punkte.

**Wahrscheinlichkeiten während des Spiels.** Robberechts, Van Haaren und Davis (2021) schätzen laufende Wahrscheinlichkeiten für Sieg, Remis und Niederlage aus dem Spielzustand (Minute, Spielstand, Stärke, Karten) und zeigen, dass Modelle aus anderen Sportarten im Fußball vor allem in der Schlussphase versagen. Ihr Modell ist die Vorlage für den Spielstandsteil von M4.

### 4.5 Trainerwirkung

Die Literatur zu Trainerwechseln findet überwiegend Rückkehr zum Mittelwert statt Wirkung. Ter Weel (2011) findet in den Niederlanden 1986–2004 keine Leistungsverbesserung nach Trainerwechseln. Van Ours und van Tuijl (2016) zeigen, dass Mannschaften sich nach einer Entlassung zwar verbessern, aber genauso eine Kontrollgruppe in vergleichbarer Lage ohne Entlassung; Entlassungen folgen Ergebnissen unter der Quotenerwartung. Muehlheusser, Schneemann und Sliwka (2016) finden Verbesserungen nur in homogenen Kadern und benennen die negative Selektion als Grund für widersprüchliche frühere Befunde. Bryson, Buraimo, Farnell und Simmons (2024) finden in vier Ländern über fünfzehn Saisonen kaum positive Effekte.

Das Strykerlabs-Trainer-Performance-Modell für die österreichische Bundesliga (Methodik vom 03.11.2026) misst die Trainerleistung als Chancenbilanz gegen den Wettmarkt und kommt zu Reliabilitäten zwischen 0,05 und 0,14. Diese Messlatte gilt auch hier: Ein Trainereffekt im ÖFB-Unterhaus ist erst behauptet, wenn er die Reliabilitätsprüfung besteht.

## 5. Der Widerspruch und seine Auflösung

### 5.1 Der Widerspruch, genau formuliert

Das Plus-Minus-Modell beantwortet: *Wie viel trägt Spieler i zum Torverhältnis bei, wenn man berücksichtigt, mit wem und gegen wen er spielt?* Es gibt der Mannschaft absichtlich keinen eigenen Term. Was eine Mannschaft leistet, wird vollständig auf die Spieler verteilt, die auf dem Feld standen.

Ein Elo-Rating beantwortet: *Wie stark ist diese Mannschaft als Ganzes?* Diese Stärke entsteht zum großen Teil aus genau denselben Spielern.

Der naheliegende Gedanke wäre, die Elo-Differenz als zusätzliche Erklärgröße in die Spieler-Regression aufzunehmen, um „die Mannschaftsstärke herauszurechnen“. Das ist falsch, aus drei Gründen:

1. **Doppelte Zählung.** Die Elo-Stärke ist eine Funktion der Leistungen der Spieler. Nimmt man sie als Regressor auf, erklärt die Elo-Differenz einen Teil dessen, was die Spieler geleistet haben, und das Modell zieht diesen Teil von den Spielern ab. Gerade die Spieler, die eine Mannschaft stark machen, verlieren am meisten.
2. **Kollinearität.** Elo ändert sich langsam und ist innerhalb einer Saison fast konstant für eine Mannschaft. Es ist damit nahezu eine Linearkombination der Indikatoren der Stammspieler. Die Schätzung wird instabil, und die Aufteilung zwischen Elo-Koeffizient und Spielerratings hängt an Zufälligkeiten.
3. **Zirkularität.** Elo verarbeitet dieselben Tore, die die Zielgröße der Spieler-Regression bilden. Ein Regressor, der aus der Zielgröße gebaut ist, verzerrt jede Kreuzvalidierung.

Formal: Sei R_T die Elo-Stärke von Mannschaft T und S_T = Σ_{i ∈ Elf} (β_i^O + β_i^D) ihre Kaderstärke. Dann gilt näherungsweise

```
R_T  ≈  a + b · S_T  +  u_T
```

u_T ist alles, was die Mannschaft über die Summe ihrer Spieler hinaus leistet: Abstimmung, System, Trainer, Zusammenhalt, Kaderbreite. Nimmt man R_T in die Spieler-Regression auf, schätzt man β unter der Bedingung, dass b · S_T schon erklärt ist. Das Rating misst dann nicht mehr den Beitrag des Spielers, sondern seine Abweichung von der Mannschaftsstärke, zu der er selbst beiträgt.

### 5.2 Die Auflösung: Elo als Maßstab, nicht als Eingabe

Der Gedanke, die Mannschaftsstärke zu nutzen, um zu erkennen, wer die Gewinnwahrscheinlichkeit positiv beeinflusst, bleibt richtig. Er gehört aber an drei andere Stellen:

**Weg A: Die Zielgröße wechseln (Baustein M4).** Statt der Tore eines Segments zählt die Veränderung der erwarteten Punkte. Ein Tor beim Stand von 0:0 in der 80. Minute verschiebt die erwarteten Punkte um rund einen Punkt, ein Tor zum 5:0 um fast nichts. Die Spieler-Regression bleibt unverändert, nur y ändert sich. So misst das Rating, wer *Spiele entscheidet*, ohne dass Elo in die Erklärgrößen eingeht. Die Vorlage ist Kharrat, McHale und López Peña (2020).

**Weg B: Segmente gewichten.** Statt die Zielgröße zu ersetzen, behält man Tore und gewichtet jedes Segment mit der *Hebelwirkung* eines Tores in diesem Spielzustand, also mit der Differenz der erwarteten Punkte nach einem eigenen und nach einem gegnerischen Tor. Entschiedene Spielphasen erhalten wenig Gewicht. Hvattum (2020) sieht solche Spielstandsgewichte ausdrücklich vor; das bestehende Modell nutzt sie nicht. Weg B ist eine Robustheitsprüfung von Weg A und bleibt in der Einheit Tore.

**Weg C: Die Differenz lesen (Baustein M3 und M5).** u_T = R_T − (a + b · S_T) ist das, was die Spielerratings nicht erklären. Es ist der beste verfügbare Kandidat für Mannschafts- und Trainereffekte. Elo und Plus-Minus werden dafür getrennt geschätzt und erst danach verglichen.

### 5.3 Ein verbleibender Rest des Widerspruchs, offen benannt

Auch Weg A braucht für die erwarteten Punkte während des Spiels eine Annahme über die Stärke beider Mannschaften. Nimmt man dafür Elo, kehrt ein Teil des Widerspruchs zurück: Ein Tor des Außenseiters bewegt die erwarteten Punkte stärker als ein Tor des Favoriten, und der Favorit ist der Favorit wegen seiner Spieler.

Deshalb wird die Hauptvariante **ohne Stärkeinformation** gerechnet: Die erwarteten Punkte hängen nur von Minute, Spielstand, Heimrecht und Spielerzahl ab. Die Stärke beider Mannschaften steckt bereits über die Gegner- und Mitspielerterme in der Regression. Eine Variante mit Elo-Ausgangswert wird nur als Sensitivitätsanalyse berichtet.

Für Weg C gilt eine zweite Einschränkung: Weil das Plus-Minus-Modell keinen Teamterm hat, ordnet es einen dauerhaften Mannschaftseffekt den Spielern zu, solange diese zusammen bleiben. u_T ist deshalb nur dort identifiziert, wo Spieler die Mannschaft wechseln oder der Trainer wechselt. Die 4 919 Spieler mit mehreren Bewerben und die 136 Trainer mit mehreren Klubs sind die Grundlage dieser Identifikation. Als Robustheitsvariante wird zusätzlich ein Plus-Minus-Modell mit regularisiertem Term je Mannschaft und Saison geschätzt (Kapitel 6.5).

## 6. Methodik der Erweiterung

### 6.1 M1: Team-Elo für ÖFB-Ergebnisse

**Aktualisierung.** Für ein Spiel zwischen Heim H und Gast A mit Stärken R_H, R_A vor dem Spiel:

```
E_H   = 1 / (1 + 10^(−(R_H + H_L − R_A) / 400))      erwartetes Ergebnis Heim
S_H   ∈ {1; 0,5; 0}                                  tatsächliches Ergebnis
G     = (1 + |Tordifferenz|)^γ                       Tordifferenz-Faktor
R_H  ← R_H + K · G · (S_H − E_H)
R_A  ← R_A − K · G · (S_H − E_H)
```

H_L ist der Heimvorteil je Kategorie (Erwachsene, Jugend), K die Lernrate, γ dämpft hohe Siege. Der Ansatz folgt der tordifferenzbasierten Variante von Hvattum und Arntzen (2010). Eine Pi-Rating-Variante (Constantinou und Fenton 2013) wird als Vergleich mitgerechnet.

**Schritt 1: Parameter schätzen.** K, γ und H_L werden nicht gesetzt, sondern durch Minimierung des RPS der Prognosen aus M2 auf einer rollierenden Stichprobe gewählt: Für jede Runde wird nur mit Spielen davor gerechnet.

**Schritt 2: Saisonübergang.** Zu Saisonbeginn wird jede Stärke zum Mittel ihres Bewerbs zurückgezogen, R ← μ_L + ρ · (R − μ_L), mit ρ aus der Kreuzvalidierung. In der **Jugend** ist das zwingend und stärker: Eine U16 besteht im Folgejahr aus einem anderen Jahrgang. Dort wird ρ getrennt geschätzt und darf nahe 0 liegen.

**Schritt 3: Neue Mannschaften.** Aufsteiger übernehmen ihre Stärke aus der Unterliga, sofern diese im Datenbestand ist; sonst starten sie beim Mittel des neuen Bewerbs minus einem geschätzten Aufsteigerabschlag.

**Schritt 4: Ligaverknüpfung.** Elo ist nur innerhalb der fünf Gruppen aus Kapitel 2.3 vergleichbar. Für Vergleiche über Gruppen hinweg wird je Bewerb ein Niveauabstand δ_L geschätzt, und zwar über die Spieler: Für Spieler mit Einsätzen in zwei Bewerben vergleicht man ihren Beitrag in beiden Umgebungen. Praktisch geschieht das, indem das Plus-Minus-Modell um einen regularisierten Term je Bewerb und Saison erweitert wird. Die Gesamtstärke ist dann R_global = R + δ_L. Ohne diesen Schritt dürfen Elo-Werte nur innerhalb einer Gruppe verglichen werden; das Dashboard muss das sichtbar machen.

**Ausgabe.** Je Mannschaft und Spiel die Stärke vor dem Spiel (für Prognosen, frei von Vorgriff auf spätere Spiele) und je Mannschaft der Verlauf über die Saison.

### 6.2 M2: Ergebniswahrscheinlichkeiten

**Hauptmodell: geordnetes Logit.** Mit x = R_H + H_L − R_A:

```
P(Heimsieg)      = 1 − F(θ_2 − α·x)
P(Remis)         = F(θ_2 − α·x) − F(θ_1 − α·x)
P(Auswärtssieg)  = F(θ_1 − α·x)                       F = logistische Verteilung
```

Die Schwellen θ_1, θ_2 werden je Kategorie geschätzt, weil die Remisquote in der Jugend um vier Prozentpunkte niedriger liegt.

**Vergleichsmodell 1: Davidson.** P(Remis) = ν·√(p_H·p_A) relativ zu den Siegwahrscheinlichkeiten (Davidson 1970); ν je Kategorie.

**Vergleichsmodell 2: Poisson-Tormodell.** Angriffs- und Abwehrstärke je Mannschaft nach Maher (1982) und Dixon und Coles (1997), mit Zeitgewichtung über eine Halbwertszeit wie bei „Total akt.“. Liefert zusätzlich eine Torverteilung je Spiel und damit Wahrscheinlichkeiten für jedes Ergebnis.

**Erwartete Punkte.** xP_H = 3·P(Heimsieg) + P(Remis), entsprechend für den Gast.

**Bewertung.** Alle Modelle werden rollierend außerhalb der Stichprobe bewertet: Prognose für Runde t nur aus Runden vor t.

| Maß | Bedeutung |
|---|---|
| RPS | Hauptmaß für geordnete Ausgänge (Epstein 1969; Constantinou und Fenton 2012) |
| logarithmischer Score | trennt schärfer bei sicheren Fehlprognosen (Wheatcroft 2021) |
| Brier-Score und Trefferquote | zur Vergleichbarkeit mit der Literatur |
| Kalibrierung | vorhergesagte gegen beobachtete Heimsiegquote in zehn Klassen; Steigung einer logistischen Regression, 1 = kalibriert |

Referenzen: Häufigkeitsprognose (RPS 0,236), Prognose nur mit Heimvorteil, Elo, Pi-Rating, Poisson. Für die Regionalligen, für die Schlussquoten beschafft werden können, wird zusätzlich gegen den Wettmarkt verglichen; dort ist zu erwarten, dass die Quoten besser sind (Hvattum und Arntzen 2010; Wunderlich und Memmert 2018).

### 6.3 M3: Kaderstärke der Startelf und Kombination

**Kaderstärke.** Für jedes Spiel und jede Mannschaft:

```
S_T(m) = Σ_{i ∈ Startelf} ( β_i^O + β_i^D ) − Ligamittel
```

Die Ratings müssen **vor dem Spiel** feststehen. Sonst enthielte S_T das Ergebnis, das vorhergesagt werden soll. Dazu werden die Ratings je Saison aus allen früheren Spielen geschätzt („gefrorene Ratings“); innerhalb einer Saison wird das Rating vom Saisonstart verwendet, in einer Variante zusätzlich monatlich nachgeschätzt. Spieler ohne Rating erhalten den Mittelwert der Neulinge ihres Bewerbs.

**Kombinationsmodell.** Geordnetes Logit mit zwei Erklärgrößen:

```
x = α_1 · (R_H + H_L − R_A)  +  α_2 · (S_H − S_A)
```

Hypothese nach Arntzen und Hvattum (2021): Das Kombinationsmodell hat einen signifikant niedrigeren RPS als jedes Einzelmodell. Getestet wird mit einem gepaarten Test auf die Differenz der RPS je Spiel (Diebold-Mariano-Prinzip).

**Zerlegung.** Aus R_T = a + b·S_T + u_T über alle Mannschaftssaisonen: Anteil der Mannschaftsstärke, den der Kader erklärt (R²), und der Mannschaftsmehrwert u_T je Mannschaft und Saison. Ein großer positiver u_T heißt: Die Mannschaft ist stärker, als ihre Spieler einzeln erwarten lassen.

### 6.4 M4: Punkte-Plus-Minus

**Erwartete Punkte im Spielverlauf.** Für jede Minute t, Tordifferenz Δ aus Sicht der Heimmannschaft, Spielerzahl und Heimrecht werden die restlichen Tore beider Mannschaften als unabhängig Poisson-verteilt angenommen:

```
Rest-Tore Heim  ~ Poisson( λ_H · (90 − t) / 90 )
Rest-Tore Gast  ~ Poisson( λ_A · (90 − t) / 90 )
EP_H(t, Δ)     = 3 · P(Endstand Heim vorne) + P(Endstand gleich)
```

λ_H und λ_A sind die mittleren Torraten der Kategorie, angepasst um Heimvorteil und Spielerzahl, aus den eigenen Daten geschätzt. Ob die Torrate in den Schlussminuten steigt, wird geprüft und gegebenenfalls als Funktion von t modelliert, weil einfache Modelle gerade dort versagen (Robberechts, Van Haaren und Davis 2021). Kalibrierung: Für jeden Spielzustand mit genügend Fällen wird EP mit den tatsächlich erzielten Punkten verglichen.

**Zielgröße.** Für jedes Tor im Segment s wird die Veränderung der erwarteten Punkte der torschießenden Mannschaft berechnet:

```
y_H^off(s) = Σ_{Tore von Heim in s}  [ EP_H(nach Tor) − EP_H(vor Tor) ]
y_A^off(s) = Σ_{Tore von Gast in s}  [ EP_A(nach Tor) − EP_A(vor Tor) ]
```

Die Design-Matrix, der Strafterm, die Kreuzvalidierung und die Zeitgewichtung bleiben unverändert. Damit bleiben Offensive und Defensive getrennt: Ein Tor gegen eine Mannschaft senkt ihre erwarteten Punkte, und dieser Verlust wird über die Defensivterme den Spielern der verteidigenden Mannschaft zugeordnet.

**Einheit.** Punkte pro 90 Minuten. Ein EP-Total von +0,10 heißt: Mit diesem Spieler gewinnt seine Mannschaft je 90 Minuten 0,1 Punkte mehr, als Mit- und Gegenspieler erwarten ließen; über 30 Spiele sind das rund drei Punkte. Die Einheit ist direkt anschlussfähig an das Ligamodell und an das Projekt Strykerlabs-Impact, das ebenfalls in Punkten je 90 Minuten rechnet.

**Weg B als Prüfung.** Zusätzlich das Tor-Rating mit Segmentgewicht w_s = Hebel(s) / mittlerer Hebel, wobei Hebel(s) = EP(eigenes Tor) − EP(Gegentor) im Zustand zu Segmentbeginn.

**Erwartung.** EP-Rating und Tor-Rating korrelieren hoch. Die Abweichungen sind der Mehrwert: Spieler, die vor allem in engen Spielen wirken, steigen; Spieler, deren Plus aus Kantersiegen stammt, fallen.

### 6.5 Robustheitsvariante: Plus-Minus mit Mannschaftsterm

Das bestehende Modell wird um einen Term je Mannschaft und Saison τ_{T,season} erweitert, der eigens und stärker regularisiert wird als die Spielerterme. Dann gilt:

- β_i misst den Beitrag des Spielers über das Niveau seiner Mannschaft hinaus,
- τ misst, was die Mannschaft unabhängig von der Besetzung leistet,
- identifiziert wird τ durch Spieler, die zwischen Mannschaften wechseln, und durch Rotation innerhalb des Kaders.

Diese Variante beantwortet dieselbe Frage wie Weg C aus einer anderen Richtung. Stimmen τ und u_T überein, ist der Mannschaftsmehrwert belastbar. Sie ist zugleich das in der Projektnotiz vorgesehene „Rating 2.0“ mit Mannschaftseffekten gegen die Übertragung starker Mannschaftsleistungen auf alle ihre Spieler.

### 6.6 M5: Trainermodul

**Schritt 1: Amtszeiten bilden.** Trainername bereinigen (Titel und Zusätze entfernen), je Mannschaft nach Datum ordnen, Folgen bilden. Eine Folge von höchstens zwei Spielen zwischen zwei Folgen desselben Trainers ist eine Vertretung und wird der umgebenden Amtszeit zugeschlagen, aber gekennzeichnet. Ein Wechsel zwischen Saisonen ohne Spiel dazwischen ist ein Sommerwechsel, sonst ein Wechsel während der Saison.

**Schritt 2: Erwartung je Spiel.** Erwartete Punkte xP aus M3, mit Stärken, die vor dem Spiel feststehen.

**Schritt 3: Kennzahlen je Amtszeit mit mindestens 20 Spielen.**

| Kennzahl | Rechnung | Lesart |
|---|---|---|
| T1 Punkte über Erwartung | Σ (Punkte − xP), z = Σ / (σ·√n) | mehr Punkte, als Stärke und Aufstellung erwarten ließen |
| T2 Mannschaftsmehrwert | Mittel von u_T über die Amtszeit, gegen den Wert vor Amtsantritt | Mannschaft stärker als die Summe der Spieler |
| T3 Kaderbereinigter Stärkeverlauf | Veränderung von R über die Amtszeit minus Veränderung durch neue Spieler (b · ΔS) | Stärkezuwachs, der nicht aus Zugängen kommt |
| T4 Spielerentwicklung | mittlere Veränderung von „Total akt.“ der eingesetzten Spieler über die Amtszeit, minus die Erwartung nach Alter | Spieler werden unter diesem Trainer besser als gleichaltrige |
| T5 Konsistenz | Vorzeichen von T1 in beiden Hälften der Amtszeit gleich | Schutz gegen einen Glücksabschnitt |

T1 entspricht dem Indikator K1 des Bundesliga-Trainermodells, mit dem Unterschied, dass hier ein Ergebnismodell statt des Wettmarkts die Erwartung setzt. T2 und T3 entsprechen K6 und der Zerlegung „Transfers gegen Entwicklung“ dort, mit Plus-Minus-Ratings anstelle von Marktwerten. Das ist der entscheidende Vorteil im Amateurbereich: Für die meisten dieser Spieler gibt es keinen Marktwert.

**Schritt 4: Pflichtprüfungen.** Ohne sie wird keine Trainerkennzahl berichtet.

- Split-Half-Reliabilität je Trainer, zufällig und zeitlich,
- Permutationstest der Varianz der Amtszeitmittel,
- Korrelation desselben Trainers bei verschiedenen Klubs (136 Trainer),
- Kontrolle der Mehrfachtests über alle Amtszeiten (False Discovery Rate),
- Ereignisstudie Trainerwechsel während der Saison: zehn Spiele davor und danach, mit einer Kontrollgruppe von Mannschaften in vergleichbarer Lage ohne Wechsel (van Ours und van Tuijl 2016). Ohne Kontrollgruppe misst die Studie die Rückkehr zum Mittelwert.

**Lesart.** Elo passt sich an: Spielt eine Mannschaft dauerhaft über Erwartung, wird das nach einigen Wochen zur neuen Erwartung und T1 läuft gegen null. T1 misst deshalb die Überraschung, T2 und T3 das Niveau. Ein Trainer hat „die Gewinnwahrscheinlichkeit erhöht“ nur, wenn T1, T2 und T3 gleichgerichtet positiv sind und die Reliabilitätsprüfung bestanden ist.

## 7. Zusammenspiel der Bausteine

| Baustein | braucht | liefert an |
|---|---|---|
| M1 Team-Elo | Ergebnisse, Datum, Bewerb | M2, M3, M5, Dashboard, MCP |
| M2 Wahrscheinlichkeiten | M1 | M3, M5, Saisonsimulation |
| M3 Kaderstärke | M1, M2, gefrorene Plus-Minus-Ratings, Startelf | M5, Prognosen mit Aufstellung |
| M4 Punkte-Plus-Minus | Segmente, Tor-Minuten, Spielstandsmodell | Scouting, Profile, Strykerlabs-Impact |
| M5 Trainer | M1–M3, Trainer je Spiel, „Total akt.“ | Trainerprofil, Trainer-Performance-Modell |
| Variante 6.5 | Segmente | Prüfung von M3 und M5, Ligaverknüpfung |

Datenfluss in der Pipeline: Die neuen Schritte laufen nach plusminus.py und vor build_db.py in update_all.py. Neue Tabellen in oefb.sqlite: team_ratings, match_probs, coach_spells, coach_metrics; neue Spalten in ratings: off_ep, def_ep, total_ep.

## 8. Grenzen und Risiken

1. **Ergebnisse sind dünne Information.** Ohne Quoten und xG gibt es je Spiel nur einen Ausgang mit rund 3,5 Toren. Die Prognosegüte bleibt deshalb hinter Bundesliga-Modellen mit Quoten zurück. Gemessen wird gegen die Häufigkeitsprognose, nicht gegen den Wettmarkt.
2. **Getrennte Ligagruppen.** Ohne Schritt 4 aus Kapitel 6.1 sind Elo-Werte aus Ost und West oder aus verschiedenen Jahrgängen nicht vergleichbar. Ein falscher Vergleich wäre der häufigste Bedienungsfehler.
3. **Jugend.** Mannschaften wechseln jährlich den Jahrgang. Elo trägt in der Jugend über die Saisongrenze kaum Information, die Kaderstärke aus Spielerratings dagegen schon.
4. **Vorgriff.** Jede Größe, die in eine Prognose eingeht, muss vor dem Spiel feststehen. Das betrifft vor allem die Spielerratings in M3. Ein Verstoß würde die Prognosegüte scheinbar verbessern.
5. **Trainerdaten.** Vertretungen, Spielertrainer, Co-Trainer im Spielbericht und Namensvarianten. Die Bereinigung aus Kapitel 6.6 ist Voraussetzung, nicht Kosmetik.
6. **Selektion.** Entlassungen folgen schlechten Ergebnissen; jede naive Vorher-nachher-Auswertung zeigt einen Scheineffekt.
7. **Kleine Stichproben.** Bei 20 bis 30 Spielen je Amtszeit ist die Unsicherheit groß. Erwartbar ist, dass nur wenige Trainer signifikant abweichen.
8. **Endstand ohne Tor-Minuten.** M4 braucht Minuten zu jedem Tor. Die Pipeline repariert fehlende Minuten bereits mit fix_events.py; Spiele, in denen das nicht gelingt, fallen aus M4 heraus und sind auszuweisen.

## 9. Mehrwerte

Die folgenden Mehrwerte sind als Hypothesen zu lesen, bis die jeweilige Abnahme in Kapitel 11 bestanden ist.

### 9.1 Für das Scouting

- **Punkte statt Tore.** Das EP-Rating zeigt, wer Spiele entscheidet. Ein Innenverteidiger, der in knappen Spielen das 1:0 hält, und ein Stürmer, der seine Tore in entschiedenen Spielen erzielt, werden erstmals unterscheidbar. Die Einheit Punkte ist für Sportdirektoren unmittelbar verständlich.
- **Vergleichbarkeit über Ligen.** Der Niveauabstand δ_L beantwortet, was ein Rating von +0,20 in der Kärntner Liga im Vergleich zur Regionalliga Ost wert ist. Bisher sind Ratings über die gemeinsame Spielerkomponente zwar formal vergleichbar, aber nicht als Ligaabstand ausgewiesen.
- **Validierte Ratings.** Wenn die Kaderstärke aus Plus-Minus-Ratings künftige Ergebnisse vorhersagt (M3), ist erstmals belegt, dass die Spielerratings Leistung messen und nicht Rauschen. Das stärkt jedes Gespräch mit Klubs über die Scouting-Liste.
- **Kontext für jeden Spieler.** Die Mannschaftsstärke zeigt, ob ein Spieler in einer dominanten oder in einer kämpfenden Mannschaft spielt, und ob seine Mannschaft über oder unter der Summe ihrer Spieler liegt.

### 9.2 Für Klubs und Sportdirektion

- **Wahrscheinlichkeiten je Spiel.** Für jedes Spiel im Datenbestand P(Sieg), P(Remis), P(Niederlage) und erwartete Punkte. Für Klubs ohne Analyseabteilung ist das die erste objektive Einordnung eines Ergebnisses: War die Niederlage Pech oder erwartbar?
- **Saisonsimulation für das Unterhaus.** Aus M2 folgen per Monte-Carlo-Simulation des Restprogramms Wahrscheinlichkeiten für Meistertitel, Aufstieg und Abstieg in jeder Landes- und Regionalliga. Für die Bundesliga leistet das bereits das Ligamodell; hier entsteht das Gegenstück für die Ligen darunter.
- **Aufstellungsabhängige Prognose.** Durch M3 ändert sich die Prognose, wenn Stammspieler fehlen. Der Wert einzelner Spieler lässt sich als Veränderung der Siegwahrscheinlichkeit ausdrücken.
- **Kaderplanung.** Die Zerlegung in Kaderstärke und Mannschaftsmehrwert zeigt, ob eine Mannschaft ihre Stärke aus Einzelspielern oder aus dem Kollektiv bezieht. Das ist relevant, wenn Leistungsträger den Klub verlassen.

### 9.3 Für die Trainerbewertung

- **Trainerbewertung ohne Quoten und xG.** Im Amateur- und Jugendbereich gibt es keine Wettmärkte und keine Eventdaten. Das Trainermodul ist dort die erste objektive Bewertung. Das bestehende Trainer-Performance-Modell deckt nur die Bundesliga ab.
- **Trainerscouting für den Profibereich.** Viele Bundesliga- und Zweitligatrainer kommen aus Regionalligen und Akademien. Für 349 Erwachsenen- und 118 Jugendamtszeiten mit mindestens 20 Spielen gibt es eine einheitliche Kennzahlensammlung. Das 136-Trainer-Panel mit mehreren Klubs zeigt, ob ein Effekt mitwandert.
- **Entwicklungswirkung.** T4 misst, ob Spieler unter einem Trainer besser werden als Gleichaltrige. Für Akademien und Ausbildungsvereine ist das die eigentlich relevante Trainerqualität.
- **Ehrliche Aussagen.** Die Pflichtprüfungen verhindern, dass Glücksphasen als Trainerqualität verkauft werden. Wenn die Reliabilität niedrig ist, ist auch das ein belastbares Ergebnis und entspricht der Literatur.

### 9.4 Für Verband, Ligen und Nachwuchs

- **Ligaabstände und Jahrgänge.** δ_L zeigt, wie weit Landesligen, Regionalligen und Jugendligen auseinanderliegen, und wie viel ein Wechsel von der U18 in die Regionalliga im Mittel kostet.
- **Wettbewerbsbalance.** Die Streuung der Elo-Werte je Liga misst, wie ausgeglichen eine Liga ist; die Remis- und Heimsiegquoten liefern die Grundwerte dazu.

### 9.5 Für das Produkt und die Methodik

- **Lücke im Gesamtbild geschlossen.** Der Kontextring „Mannschaft“ im Strykerlabs-Onepager ist bisher offen. M1 bis M3 füllen ihn.
- **Anschluss an bestehende Modelle.** Punkte je 90 Minuten verbindet das ÖFB-Modell mit Strykerlabs-Impact und dem Ligamodell. Das Trainermodul nutzt dieselbe Logik und dieselben Prüfungen wie das Bundesliga-Trainermodell und überträgt sie in Ligen ohne Markt.
- **Neue Werkzeuge für den MCP-Zugang.** Team-Rating, Spielprognose, Trainerprofil und Saisonsimulation als Werkzeuge für Agenten und Analysten.
- **Wissenschaftlicher Beitrag.** Eine Prüfung von Arntzen und Hvattum (2021) in Amateur- und Jugendligen und eine Trainerbewertung über Plus-Minus-Kaderstärke statt Marktwerten sind nach unserem Kenntnisstand nicht publiziert.

## 10. Abgrenzung

Nicht Teil dieser Erweiterung: Wettquoten als Eingangsgröße, xG, Eventdaten über Tore und Karten hinaus, die Bundesliga und 2. Liga, sowie eine eigene Schätzung der Alterskurve. Diese Punkte bleiben eigene Vorhaben.

## 11. Umsetzungsplan

Die Umsetzung ist noch nicht begonnen. Jede Phase endet mit einer Abnahme; nach Phase 1 und Phase 3 wird entschieden, ob weitergebaut wird. Die Aufwände sind grobe Schätzungen in Arbeitstagen.

| Phase | Inhalt | Ergebnis | Abnahme | Aufwand |
|---|---|---|---|---|
| P0 Datenaufbereitung | Trainernamen bereinigen, Amtszeiten mit Vertretungsregel, Mannschaftsnamen über Saisonen vereinheitlichen, Ligagruppen ausweisen, Spiele ohne Tor-Minuten zählen | coach_spells, Prüfbericht | Stichprobe von 30 Amtszeiten gegen oefb.at geprüft, Fehlerquote unter 5 % | 2–3 |
| P1 Team-Elo und Wahrscheinlichkeiten | M1 und M2, rollierende Bewertung, Pi-Rating und Poisson als Vergleich | team_ratings, match_probs, Gütebericht | RPS deutlich unter 0,236; Kalibrierungssteigung zwischen 0,9 und 1,1 je Kategorie | 3–4 |
| **Entscheidung 1** | Ist die Prognosegüte ausreichend für Anwendungen? | | | |
| P2 Ligaverknüpfung | Plus-Minus mit Term je Bewerb und Saison, δ_L, globale Stärke | Ligaabstände, R_global | Ligaabstände plausibel zu Auf- und Abstiegsergebnissen; stabil bei Teilstichproben | 2–3 |
| P3 Kaderstärke und Kombination | gefrorene Ratings je Saison, Kaderstärke der Startelf, Kombinationsmodell, Zerlegung, Variante mit Mannschaftsterm | Kombinationsprognose, u_T, τ | Kombination signifikant besser als Elo allein; Korrelation u_T und τ berichtet | 3–4 |
| **Entscheidung 2** | Tragen die Spielerratings Prognoseinformation? Wenn nein: Plus-Minus-Modell überarbeiten, bevor M4 und M5 darauf aufbauen | | | |
| P4 Punkte-Plus-Minus | Spielstandsmodell, Kalibrierung, EP-Zielgröße, Variante mit Hebelgewichten | off_ep, def_ep, total_ep | Spielstandsmodell kalibriert; Korrelation zum Tor-Rating berichtet; zehn größte Auf- und Absteiger fachlich plausibel | 3 |
| P5 Trainermodul | T1 bis T5, Pflichtprüfungen, Ereignisstudie mit Kontrollgruppe | coach_metrics, Methodenbericht | alle Pflichtprüfungen gerechnet und berichtet, auch wenn sie negativ ausfallen | 4–5 |
| P6 Integration | Tabellen in build_db.py, Spalten in scout.json (Version 4), Dashboard-Reiter „Mannschaften“ und „Trainer“, Spalte „EP-Total“, MCP-Werkzeuge, Aufnahme in update_all.py | lokal geprüftes Dashboard | Browserprüfung wie bei „Total akt.“; alte scout.json blendet neue Teile aus | 3–4 |
| P7 Validierungsbericht | Ergebnisse zu F1 bis F4 als Fortschreibung dieses Dokuments | Bericht | Durchsicht durch Fachseite | 2 |

Gesamt rund 22 bis 28 Arbeitstage. Für den Deploy gilt die bestehende Reihenfolge: zuerst die Daten hochladen, dann den Code pushen.

**Neue Programmteile.** team_elo.py (M1, M2), lineup_strength.py (M3), Spielstands- und EP-Zielgröße als Option von plusminus.py (M4), coaches.py (P0, M5). Alle neuen Schritte schreiben wie plusminus.py zuerst Dateien in data/ und werden von build_db.py in die Datenbank übernommen.

## 12. Literatur

Arntzen, H. und Hvattum, L. M. (2021). Predicting match outcomes in association football using team ratings and player ratings. *Statistical Modelling*, 21(5), 449–470. doi:10.1177/1471082X20929881

Bryson, A., Buraimo, B., Farnell, A. und Simmons, R. (2024). Special ones? The effect of head coaches on football team performance. *Scottish Journal of Political Economy*, 71(3), 295–322. Arbeitspapier: IZA DP 14104 (2021).

Constantinou, A. C. und Fenton, N. E. (2012). Solving the problem of inadequate scoring rules for assessing probabilistic football forecast models. *Journal of Quantitative Analysis in Sports*, 8(1). doi:10.1515/1559-0410.1418

Constantinou, A. C. und Fenton, N. E. (2013). Determining the level of ability of football teams by dynamic ratings based on the relative discrepancies in scores between adversaries. *Journal of Quantitative Analysis in Sports*, 9(1), 37–50. doi:10.1515/jqas-2012-0036

Davidson, R. R. (1970). On extending the Bradley-Terry model to accommodate ties in paired comparison experiments. *Journal of the American Statistical Association*, 65, 317–328. doi:10.1080/01621459.1970.10481082

Dixon, M. J. und Coles, S. G. (1997). Modelling association football scores and inefficiencies in the football betting market. *Journal of the Royal Statistical Society, Series C (Applied Statistics)*, 46(2), 265–280. doi:10.1111/1467-9876.00065

Dubitzky, W., Lopes, P., Davis, J. und Berrar, D. (2019). The Open International Soccer Database for machine learning. *Machine Learning*, 108(1), 9–28. doi:10.1007/s10994-018-5726-0

Epstein, E. S. (1969). A scoring system for probability forecasts of ranked categories. *Journal of Applied Meteorology*, 8, 985–987.

Hvattum, L. M. (2019). A comprehensive review of plus-minus ratings for evaluating individual players in team sports. *International Journal of Computer Science in Sport*, 18(1), 1–23. doi:10.2478/ijcss-2019-0001

Hvattum, L. M. (2020). Offensive and defensive plus-minus player ratings for soccer. *Applied Sciences*, 10(20), 7345. doi:10.3390/app10207345

Hvattum, L. M. und Arntzen, H. (2010). Using ELO ratings for match result prediction in association football. *International Journal of Forecasting*, 26(3), 460–470. doi:10.1016/j.ijforecast.2009.10.002

Hvattum, L. M., Kriegl, M.-A. und Čulík, M. (2023). Identifying talent with plus-minus ratings in association football. In Y. Dominicy und C. Ley (Hrsg.), *Statistics Meets Sports: What We Can Learn from Sports Data* (S. 175–200). Cambridge Scholars Publishing.

Ilardi, S. (2007). Adjusted plus-minus: An idea whose time has come. 82games.com.

Kharrat, T., McHale, I. G. und López Peña, J. (2020). Plus-minus player ratings for soccer. *European Journal of Operational Research*, 283(2), 726–736.

Lasek, J., Szlávik, Z. und Bhulai, S. (2013). The predictive power of ranking systems in association football. *International Journal of Applied Pattern Recognition*, 1(1), 27–46.

Ley, C., Van de Wiele, T. und Van Eetvelde, H. (2019). Ranking soccer teams on the basis of their current strength: A comparison of maximum likelihood approaches. *Statistical Modelling*, 19(1), 55–73.

Maher, M. J. (1982). Modelling association football scores. *Statistica Neerlandica*, 36(3), 109–118. doi:10.1111/j.1467-9574.1982.tb00782.x

Muehlheusser, G., Schneemann, S. und Sliwka, D. (2016). The impact of managerial change on performance: The role of team heterogeneity. *Economic Inquiry*, 54(2), 1128–1149. doi:10.1111/ecin.12285

Robberechts, P., Van Haaren, J. und Davis, J. (2021). A Bayesian approach to in-game win probability in soccer. In *Proceedings of the 27th ACM SIGKDD Conference on Knowledge Discovery and Data Mining*, 3512–3521.

Štrumbelj, E. (2014). On determining probability forecasts from betting odds. *International Journal of Forecasting*, 30(4), 934–943.

ter Weel, B. (2011). Does manager turnover improve firm performance? Evidence from Dutch soccer, 1986–2004. *De Economist*, 159(3), 279–303.

van Ours, J. C. und van Tuijl, M. A. (2016). In-season head-coach dismissals and the performance of professional football teams. *Economic Inquiry*, 54(1), 591–604.

Wheatcroft, E. (2021). Evaluating probabilistic forecasts of football matches: The case against the ranked probability score. *Journal of Quantitative Analysis in Sports*, 17(4), 273–287. doi:10.1515/jqas-2019-0089

Wunderlich, F. und Memmert, D. (2018). The betting odds rating system: Using soccer forecasts to forecast soccer. *PLOS ONE*, 13(6), e0198668. doi:10.1371/journal.pone.0198668

**Interne Bezüge.** plusminus.py und DASHBOARD-DATA.md in diesem Projekt; Trainer-Performance-Modell, Methodik und Übertragung auf andere Ligen (Strykerlabs, 03.11.2026), im Projekt Kontexttransfer; Projekt-Onepager (Strykerlabs, Stand 08.11.2026).

**Hinweis zur Quellenlage.** Bibliografische Angaben wurden am 11.11.2026 online gegen Verlags- und Repositoriumseinträge geprüft. Die Talent-Studie von Hvattum, Kriegl und Čulík ist ein Buchkapitel von 2023; das Dashboard nannte bisher 2021 und einen abweichenden Titel. Ilardi (2007) ist ein Fachartikel ohne Begutachtung.

## Anhang A: Notation

| Symbol | Bedeutung |
|---|---|
| β_i^O, β_i^D | Offensiv- und Defensivrating von Spieler i, Tore pro 90 Minuten |
| λ | Regularisierungsstärke der Plus-Minus-Regression |
| w | Segmentgewicht (Zeit oder Spielstand) |
| R_T | Elo-Stärke von Mannschaft T vor einem Spiel |
| H_L | Heimvorteil je Kategorie in Elo-Punkten |
| K, γ, ρ | Lernrate, Dämpfung der Tordifferenz, Rückzug zum Mittel beim Saisonwechsel |
| δ_L | Niveauabstand von Bewerb L |
| S_T | Kaderstärke der Startelf aus gefrorenen Plus-Minus-Ratings |
| u_T | Mannschaftsmehrwert über die Kaderstärke hinaus |
| τ_{T,season} | Mannschaftsterm in der Robustheitsvariante |
| EP | erwartete Punkte, 3·P(Sieg) + P(Remis) |
| xP | erwartete Punkte vor dem Spiel |
| RPS | Ranked Probability Score, kleiner ist besser |

## Anhang B: Herleitung der Kennzahlen in Kapitel 2

Alle Werte aus data/oefb.sqlite und data/matches.csv, Stand 07.11.2026. Ligagruppen über Mannschaften: zwei Bewerbe gelten als verbunden, wenn eine Mannschaft unter gleichem Namen in beiden gespielt hat; über Spieler: wenn ein Spieler mit Spielminuten in beiden eingesetzt wurde. Kategorie Jugend: Bewerbsname enthält „U“ mit Ziffer oder „Jugend“. Trainerfolgen: je Mannschaft und Kategorie nach Datum geordnet, Trainername wie im Spielbericht. Die Häufigkeitsprognose verwendet die Gesamtquoten 46,4 / 20,0 / 33,6 % für alle 12 824 Spiele mit Endstand.
