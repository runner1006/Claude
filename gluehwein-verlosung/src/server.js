'use strict';
const http = require('node:http');
const crypto = require('node:crypto');
const path = require('node:path');
const QRCode = require('qrcode');
const D = require('./db');
const V = require('./views');

function konfiguration(env = process.env) {
  const zufall = () => crypto.randomBytes(9).toString('base64url');
  const cfg = {
    port: Number(env.PORT) || 3000,
    datei: env.DB_FILE || path.join(env.DATA_DIR || path.join(__dirname, '..', 'data'), 'verlosung.sqlite'),
    standPin: env.STAND_PIN || '',
    adminPasswort: env.ADMIN_PASSWORD || '',
    publicUrl: (env.PUBLIC_URL || '').replace(/\/+$/, ''),
    veranstalter: env.VERANSTALTER || 'Glühweinstand',
    kontakt: env.KONTAKT_EMAIL || 'kontakt@example.at',
    erzeugt: [],
  };
  // Keine unsicheren Standardwerte: fehlende Zugangsdaten werden zufällig erzeugt und im Log ausgegeben.
  if (!cfg.standPin) { cfg.standPin = zufall(); cfg.erzeugt.push(`STAND_PIN=${cfg.standPin}`); }
  if (!cfg.adminPasswort) { cfg.adminPasswort = zufall(); cfg.erzeugt.push(`ADMIN_PASSWORD=${cfg.adminPasswort}`); }
  cfg.geheimnis = env.SESSION_SECRET || crypto.createHash('sha256').update(`sitzung|${cfg.standPin}|${cfg.adminPasswort}`).digest('hex');
  return cfg;
}

function gleich(a, b) {
  const x = crypto.createHash('sha256').update(String(a)).digest();
  const y = crypto.createHash('sha256').update(String(b)).digest();
  return crypto.timingSafeEqual(x, y);
}

const SITZUNG_STUNDEN = 14;

function erstelleApp(cfg, db) {
  const versuche = new Map(); // IP -> [Zeitstempel]

  function signiere(rolle) {
    const ablauf = Date.now() + SITZUNG_STUNDEN * 3600e3;
    const daten = `${rolle}.${ablauf}`;
    const mac = crypto.createHmac('sha256', cfg.geheimnis).update(daten).digest('base64url');
    return `${daten}.${mac}`;
  }

  function rolleVon(req) {
    const m = /(?:^|;\s*)sitzung=([^;]+)/.exec(req.headers.cookie || '');
    if (!m) return null;
    const [rolle, ablauf, mac] = m[1].split('.');
    if (!rolle || !ablauf || !mac) return null;
    const soll = crypto.createHmac('sha256', cfg.geheimnis).update(`${rolle}.${ablauf}`).digest('base64url');
    if (!gleich(mac, soll) || Number(ablauf) < Date.now()) return null;
    return rolle === 'admin' || rolle === 'stand' ? rolle : null;
  }

  const darfStand = (r) => r === 'stand' || r === 'admin';

  function ip(req) {
    const xff = req.headers['x-forwarded-for'];
    return (xff ? String(xff).split(',')[0].trim() : '') || req.socket.remoteAddress || '?';
  }

  function gebremst(req) {
    const k = ip(req);
    const seit = Date.now() - 10 * 60e3;
    const liste = (versuche.get(k) || []).filter((t) => t > seit);
    versuche.set(k, liste);
    if (liste.length >= 10) return true;
    liste.push(Date.now());
    return false;
  }

  function basisUrl(req) {
    if (cfg.publicUrl) return cfg.publicUrl;
    const proto = req.headers['x-forwarded-proto'] || 'http';
    return `${proto}://${req.headers.host}`;
  }

  const qr = (req, token) => QRCode.toString(`${basisUrl(req)}/l/${token}`, { type: 'svg', margin: 1, errorCorrectionLevel: 'M' });

  function sende(res, status, typ, inhalt, kopf = {}) {
    res.writeHead(status, {
      'Content-Type': typ,
      'Cache-Control': 'no-store',
      'Referrer-Policy': 'no-referrer',
      'X-Content-Type-Options': 'nosniff',
      'X-Frame-Options': 'DENY',
      'X-Robots-Tag': 'noindex, nofollow',
      ...kopf,
    });
    res.end(inhalt);
  }
  const html = (res, inhalt, status = 200, kopf) => sende(res, status, 'text/html; charset=utf-8', inhalt, kopf);
  const json = (res, obj, status = 200) => sende(res, status, 'application/json; charset=utf-8', JSON.stringify(obj));

  function koerper(req) {
    return new Promise((ok, fehler) => {
      let daten = '';
      req.on('data', (c) => {
        daten += c;
        if (daten.length > 20000) { fehler(new Error('zu groß')); req.destroy(); }
      });
      req.on('end', () => ok(daten));
      req.on('error', fehler);
    });
  }

  async function jsonKoerper(req) {
    if (!/^application\/json/i.test(req.headers['content-type'] || '')) return null;
    try {
      const o = JSON.parse(await koerper(req));
      return o && typeof o === 'object' ? o : null;
    } catch {
      return null;
    }
  }

  function pruefePerson(b) {
    const s = (x) => (typeof x === 'string' ? x.trim().replace(/\s+/g, ' ') : '');
    const p = { vorname: s(b.vorname), nachname: s(b.nachname), email: s(b.email).toLowerCase(), telefon: s(b.telefon) };
    if (p.vorname.length < 1 || p.vorname.length > 80) return { fehler: 'Bitte gib deinen Vornamen an.', feld: 'vorname' };
    if (p.nachname.length < 1 || p.nachname.length > 80) return { fehler: 'Bitte gib deinen Nachnamen an.', feld: 'nachname' };
    if (p.email.length > 160 || !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(p.email)) return { fehler: 'Bitte prüfe deine E-Mail-Adresse.', feld: 'email' };
    if (p.telefon.length > 30 || !/^[+0-9][0-9 ()/.-]*$/.test(p.telefon) || p.telefon.replace(/\D/g, '').length < 6)
      return { fehler: 'Bitte prüfe deine Telefonnummer.', feld: 'telefon' };
    if (b.einwilligung !== true) return { fehler: 'Bitte bestätige die Datenschutzerklärung.', feld: 'einwilligung' };
    return { person: p };
  }

  function codeAnsicht(c) {
    const status = D.codeStatus(c);
    let name = null;
    if (status === 'eingeloest') {
      const t = db.prepare('SELECT vorname, nachname FROM teilnahmen WHERE token = ?').get(c.token);
      if (t) name = `${t.vorname} ${t.nachname.charAt(0)}.`;
    }
    return { token: c.token, lose: c.lose, erstellt: c.erstellt, status, name };
  }

  const wienTag = (d) => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Vienna' }).format(new Date(d));

  function csv(zeilen) {
    const zelle = (w) => {
      let s = String(w ?? '');
      if (/^[=\-@\t\r]/.test(s) || (/^\+/.test(s) && !/^\+[0-9 ()/.-]+$/.test(s))) s = `'${s}`;
      return `"${s.replace(/"/g, '""')}"`;
    };
    return '﻿' + zeilen.map((z) => z.map(zelle).join(';')).join('\r\n') + '\r\n';
  }

  async function behandle(req, res) {
    const url = new URL(req.url, 'http://x');
    const pfad = url.pathname;
    const m = req.method;
    const rolle = rolleVon(req);

    // ---------- Öffentlich ----------
    if (m === 'GET' && pfad === '/') return html(res, V.start(cfg));
    if (m === 'GET' && pfad === '/datenschutz') return html(res, V.datenschutz(cfg));
    if (m === 'GET' && pfad === '/healthz') return sende(res, 200, 'text/plain', 'ok');

    if (m === 'GET' && pfad.startsWith('/l/')) {
      const code = D.codeHolen(db, decodeURIComponent(pfad.slice(3)));
      const status = D.codeStatus(code);
      if (status === 'offen') return html(res, V.formular(code, cfg));
      if (status === 'eingeloest')
        return html(res, V.hinweis('Code bereits eingelöst', 'Mit diesem Code wurde schon eine Eintragung gemacht. Jeder Code gilt genau einmal. Wenn du das selbst warst: Du bist dabei, alles gut!', cfg), 410);
      return html(res, V.hinweis('Code ungültig', 'Diesen Code kennen wir nicht. Bitte wende dich an das Team am Stand.', cfg), 404);
    }

    if (m === 'POST' && pfad === '/api/einloesen') {
      const b = await jsonKoerper(req);
      if (!b || typeof b.token !== 'string') return json(res, { fehler: 'Ungültige Anfrage.' }, 400);
      const p = pruefePerson(b);
      if (p.fehler) return json(res, p, 400);
      const r = D.einloesen(db, b.token, p.person);
      if (!r.ok)
        return json(res, { fehler: r.grund === 'eingeloest' ? 'Dieser Code wurde bereits eingelöst.' : 'Dieser Code ist ungültig.' }, 409);
      return json(res, { ok: true, lose: r.lose });
    }

    // ---------- Anmeldung ----------
    if (m === 'POST' && pfad === '/login') {
      const f = new URLSearchParams(await koerper(req));
      const ziel = f.get('rolle') === 'admin' ? 'admin' : 'stand';
      if (gebremst(req)) return html(res, V.login(ziel, 'Zu viele Versuche. Bitte in 10 Minuten noch einmal.'), 429);
      const pw = f.get('pw') || '';
      const ok = ziel === 'admin' ? gleich(pw, cfg.adminPasswort) : gleich(pw, cfg.standPin) || gleich(pw, cfg.adminPasswort);
      if (!ok) return html(res, V.login(ziel, 'Das war leider falsch.'), 401);
      const sicher = (req.headers['x-forwarded-proto'] || '') === 'https' ? '; Secure' : '';
      res.writeHead(303, {
        Location: ziel === 'admin' ? '/admin' : '/stand',
        'Set-Cookie': `sitzung=${signiere(ziel)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${SITZUNG_STUNDEN * 3600}${sicher}`,
      });
      return res.end();
    }
    if (m === 'GET' && pfad === '/logout') {
      res.writeHead(303, { Location: '/', 'Set-Cookie': 'sitzung=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0' });
      return res.end();
    }

    // ---------- Stand ----------
    if (m === 'GET' && pfad === '/stand') return darfStand(rolle) ? html(res, V.stand()) : html(res, V.login('stand'), 401);
    if (m === 'GET' && pfad === '/admin') return rolle === 'admin' ? html(res, V.admin()) : html(res, V.login('admin'), 401);

    const istApi = pfad.startsWith('/api/');
    if (istApi && m === 'POST' && req.headers['x-requested-with'] !== 'fetch') return json(res, { fehler: 'Ungültige Anfrage.' }, 400);

    if (pfad.startsWith('/api/stand/')) {
      if (!darfStand(rolle)) return json(res, { fehler: 'Nicht angemeldet.' }, 401);

      if (m === 'POST' && pfad === '/api/stand/code') {
        const b = await jsonKoerper(req);
        const lose = b && Number(b.lose);
        if (!Object.hasOwn(D.PAKETE, lose)) return json(res, { fehler: 'Ungültige Losanzahl.' }, 400);
        const token = D.codeAnlegen(db, lose, 'stand');
        return json(res, { ...codeAnsicht(D.codeHolen(db, token)), svg: await qr(req, token) });
      }
      if (m === 'GET' && pfad.startsWith('/api/stand/code/')) {
        const c = D.codeHolen(db, decodeURIComponent(pfad.slice('/api/stand/code/'.length)));
        if (!c) return json(res, { fehler: 'Unbekannt.' }, 404);
        const a = codeAnsicht(c);
        if (a.status === 'offen' && !url.searchParams.has('ohneqr')) a.svg = await qr(req, c.token);
        return json(res, a);
      }
      if (m === 'GET' && pfad === '/api/stand/codes') {
        const alle = db.prepare("SELECT * FROM codes WHERE quelle = 'stand' ORDER BY erstellt DESC").all();
        const heute = wienTag(Date.now());
        const h = alle.filter((c) => !c.storniert && wienTag(c.erstellt) === heute);
        return json(res, {
          codes: alle.slice(0, 15).map(codeAnsicht),
          heute: { verkaeufe: h.length, lose: h.reduce((s, c) => s + c.lose, 0), cent: h.reduce((s, c) => s + c.preis_cent, 0) },
        });
      }
      if (m === 'POST' && pfad === '/api/stand/storno') {
        const b = await jsonKoerper(req);
        return json(res, { ok: !!b && D.codeStornieren(db, b.token) });
      }
    }

    // ---------- Verwaltung ----------
    if (pfad.startsWith('/api/admin/') || pfad.startsWith('/admin/')) {
      if (rolle !== 'admin') return istApi ? json(res, { fehler: 'Nicht angemeldet.' }, 401) : html(res, V.login('admin'), 401);

      if (m === 'GET' && pfad === '/api/admin/uebersicht') {
        return json(res, {
          statistik: D.statistik(db),
          teilnahmen: db.prepare('SELECT vorname, nachname, email, telefon, lose, einwilligung_am FROM teilnahmen ORDER BY id DESC').all(),
          ziehungen: db.prepare('SELECT * FROM ziehungen ORDER BY id').all(),
          chargen: db
            .prepare("SELECT charge, COUNT(*) codes, SUM(eingeloest_am IS NOT NULL) eingeloest FROM codes WHERE quelle = 'druck' GROUP BY charge ORDER BY MIN(erstellt)")
            .all(),
        });
      }
      if (m === 'GET' && pfad === '/admin/export.csv') {
        const z = db.prepare('SELECT * FROM teilnahmen ORDER BY id').all();
        const inhalt = csv([
          ['Vorname', 'Nachname', 'E-Mail', 'Telefon', 'Lose', 'Eingetragen am', 'Einwilligung Datenschutz'],
          ...z.map((t) => [t.vorname, t.nachname, t.email, t.telefon, t.lose, t.einwilligung_am, 'ja']),
        ]);
        return sende(res, 200, 'text/csv; charset=utf-8', inhalt, { 'Content-Disposition': 'attachment; filename="verlosung-teilnehmer.csv"' });
      }
      if (m === 'POST' && pfad === '/api/admin/ziehen') {
        const b = (await jsonKoerper(req)) || {};
        const z = D.ziehen(db, { preis: typeof b.preis === 'string' ? b.preis.trim() : '', mehrfachgewinn: b.mehrfachgewinn === true });
        if (!z) return json(res, { fehler: 'Es ist niemand (mehr) im Topf.' }, 409);
        return json(res, z);
      }
      if (m === 'POST' && pfad === '/api/admin/ziehungen-zuruecksetzen') {
        db.exec('DELETE FROM ziehungen');
        return json(res, { ok: true });
      }
      if (m === 'POST' && pfad === '/api/admin/druckcharge') {
        const b = (await jsonKoerper(req)) || {};
        const einzel = Math.trunc(Number(b.einzel)) || 0;
        const buendel = Math.trunc(Number(b.buendel)) || 0;
        if (einzel < 0 || buendel < 0 || einzel > 500 || buendel > 500 || einzel + buendel === 0)
          return json(res, { fehler: 'Bitte Anzahl zwischen 0 und 500 angeben.' }, 400);
        const n = db.prepare("SELECT COUNT(DISTINCT charge) n FROM codes WHERE quelle = 'druck'").get().n;
        const charge = `D${String(n + 1).padStart(2, '0')}`;
        for (let i = 0; i < einzel; i++) D.codeAnlegen(db, 1, 'druck', charge);
        for (let i = 0; i < buendel; i++) D.codeAnlegen(db, 5, 'druck', charge);
        return json(res, { charge });
      }
      if (m === 'GET' && pfad.startsWith('/admin/druck/')) {
        const charge = decodeURIComponent(pfad.slice('/admin/druck/'.length));
        const codes = db
          .prepare("SELECT * FROM codes WHERE quelle = 'druck' AND charge = ? AND eingeloest_am IS NULL AND storniert = 0 ORDER BY lose, rowid")
          .all(charge);
        const karten = await Promise.all(codes.map(async (c) => ({ lose: c.lose, svg: await qr(req, c.token) })));
        return html(res, V.druckbogen(charge, karten, cfg));
      }
      if (m === 'POST' && pfad === '/api/admin/alles-loeschen') {
        const b = (await jsonKoerper(req)) || {};
        if (b.bestaetigung !== 'LÖSCHEN') return json(res, { fehler: 'Nicht bestätigt.' }, 400);
        db.exec('DELETE FROM ziehungen; DELETE FROM teilnahmen; DELETE FROM codes;');
        return json(res, { ok: true });
      }
    }

    return istApi ? json(res, { fehler: 'Nicht gefunden.' }, 404) : html(res, V.hinweis('Seite nicht gefunden', 'Diese Seite gibt es nicht.', cfg), 404);
  }

  return http.createServer((req, res) => {
    behandle(req, res).catch((e) => {
      console.error(e);
      if (!res.headersSent) json(res, { fehler: 'Interner Fehler.' }, 500);
      else res.end();
    });
  });
}

if (require.main === module) {
  const cfg = konfiguration();
  const db = D.oeffnen(cfg.datei);
  erstelleApp(cfg, db).listen(cfg.port, () => {
    console.log(`Glühwein-Verlosung läuft auf Port ${cfg.port}, Datenbank: ${cfg.datei}`);
    if (cfg.erzeugt.length) console.log(`Keine Zugangsdaten gesetzt – für diesen Start erzeugt:\n  ${cfg.erzeugt.join('\n  ')}`);
  });
}

module.exports = { konfiguration, erstelleApp };
