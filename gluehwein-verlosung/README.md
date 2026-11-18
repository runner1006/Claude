# Glühwein-Verlosung

Kleine Web-App für den Losverkauf am Glühweinstand. Eigenständiges Projekt, hat mit dem restlichen Repository nichts zu tun.

## Ablauf

1. **Stand** (`/stand`, mit Stand-PIN): Nach dem Kassieren tippt das Team auf „1 Los (€ 5)“ oder „5 Lose (€ 20)“. Am Handy erscheint ein QR-Code.
2. **Kund:in** scannt den QR-Code mit der eigenen Handykamera, trägt Vorname, Nachname, E-Mail und Telefon ein und bestätigt die Datenschutzerklärung. Am Stand-Handy erscheint „✓ Eingetragen“.
3. **Verwaltung** (`/admin`, mit Passwort): Teilnehmerliste, CSV-Export, Ziehung, Druckbögen, Löschen aller Daten.

Alternative zu Schritt 1: In der Verwaltung Kärtchen mit Einmal-Codes drucken und beim Kauf aushändigen.

## Regeln, die die App durchsetzt

- Ein Code entsteht nur am angemeldeten Stand-Gerät (oder als Druckkärtchen) und gilt **genau einmal**. Ein weitergegebener Link oder ein Foto des QR-Codes ist nach der ersten Eintragung wertlos.
- Es gibt nur Codes für 1 oder 5 Lose.
- Jedes Los hat dieselbe Gewinnchance; 5 Lose liegen 5-mal im Topf. Mehrere Käufe derselben Person (gleiche E-Mail) zählen zusammen.
- Gezogen wird mit dem kryptografischen Zufallsgenerator des Systems. Wer gewonnen hat, fällt standardmäßig aus dem Topf (umschaltbar).
- Jede Ziehung wird mit Zeit und Topfgröße protokolliert.

## Starten

```
npm install
cp .env.example .env   # Werte eintragen
node --env-file=.env src/server.js
npm test
```

Benötigt Node.js ab 22.13. Einstellungen siehe `.env.example`. Ohne `STAND_PIN` / `ADMIN_PASSWORD` erzeugt die App beim Start zufällige Zugangsdaten und schreibt sie ins Log.

## Betrieb

- Die Daten liegen in einer SQLite-Datei unter `DATA_DIR`. Dieser Ordner **muss auf dauerhaftem Speicher liegen** (z. B. Render mit Persistent Disk, Fly.io-Volume, eigener Server). Auf Gratis-Hostings ohne Disk gehen die Daten bei jedem Neustart verloren.
- HTTPS ist Pflicht (macht üblicherweise das Hosting). `PUBLIC_URL` auf die öffentliche Adresse setzen, sie steht im QR-Code.
- Vor dem Start die Datenschutzerklärung (`/datenschutz`, Text in `src/views.js`) prüfen und `VERANSTALTER` / `KONTAKT_EMAIL` setzen.
