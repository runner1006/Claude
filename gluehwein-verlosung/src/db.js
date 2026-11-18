'use strict';
// Datenhaltung und Geschäftslogik: Codes, Teilnahmen, Ziehung.
const { DatabaseSync } = require('node:sqlite');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

// Erlaubte Pakete: Anzahl Lose -> Preis in Cent
const PAKETE = { 1: 500, 5: 2000 };

function jetzt() {
  return new Date().toISOString();
}

function neuerToken() {
  return crypto.randomBytes(16).toString('base64url');
}

function oeffnen(datei) {
  if (datei !== ':memory:') fs.mkdirSync(path.dirname(datei), { recursive: true });
  const db = new DatabaseSync(datei);
  db.exec(`
    PRAGMA journal_mode = WAL;
    PRAGMA foreign_keys = ON;
    CREATE TABLE IF NOT EXISTS codes (
      token         TEXT PRIMARY KEY,
      lose          INTEGER NOT NULL,
      preis_cent    INTEGER NOT NULL,
      quelle        TEXT NOT NULL,          -- 'stand' (live erzeugt) oder 'druck' (vorgedruckt)
      charge        TEXT,                   -- Druckcharge, nur bei quelle = 'druck'
      erstellt      TEXT NOT NULL,
      storniert     INTEGER NOT NULL DEFAULT 0,
      eingeloest_am TEXT
    );
    CREATE TABLE IF NOT EXISTS teilnahmen (
      id              INTEGER PRIMARY KEY AUTOINCREMENT,
      token           TEXT NOT NULL UNIQUE REFERENCES codes(token),
      vorname         TEXT NOT NULL,
      nachname        TEXT NOT NULL,
      email           TEXT NOT NULL,
      telefon         TEXT NOT NULL,
      lose            INTEGER NOT NULL,
      einwilligung_am TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS ziehungen (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      email         TEXT NOT NULL,
      vorname       TEXT NOT NULL,
      nachname      TEXT NOT NULL,
      telefon       TEXT NOT NULL,
      lose          INTEGER NOT NULL,
      preis         TEXT NOT NULL DEFAULT '',
      pool_lose     INTEGER NOT NULL,
      pool_personen INTEGER NOT NULL,
      gezogen_am    TEXT NOT NULL
    );
  `);
  return db;
}

function codeAnlegen(db, lose, quelle, charge = null) {
  if (!Object.hasOwn(PAKETE, lose)) throw new Error('Ungültige Losanzahl');
  const token = neuerToken();
  db.prepare(
    'INSERT INTO codes (token, lose, preis_cent, quelle, charge, erstellt) VALUES (?, ?, ?, ?, ?, ?)'
  ).run(token, lose, PAKETE[lose], quelle, charge, jetzt());
  return token;
}

function codeHolen(db, token) {
  return db.prepare('SELECT * FROM codes WHERE token = ?').get(String(token)) || null;
}

// 'offen' | 'eingeloest' | 'storniert' | 'unbekannt'
function codeStatus(code) {
  if (!code) return 'unbekannt';
  if (code.storniert) return 'storniert';
  if (code.eingeloest_am) return 'eingeloest';
  return 'offen';
}

function codeStornieren(db, token) {
  const r = db
    .prepare('UPDATE codes SET storniert = 1 WHERE token = ? AND eingeloest_am IS NULL AND storniert = 0')
    .run(String(token));
  return r.changes === 1;
}

// Löst einen Code genau einmal ein. Gibt { ok, lose } oder { ok:false, grund } zurück.
function einloesen(db, token, person) {
  db.exec('BEGIN IMMEDIATE');
  try {
    const zeit = jetzt();
    const r = db
      .prepare('UPDATE codes SET eingeloest_am = ? WHERE token = ? AND eingeloest_am IS NULL AND storniert = 0')
      .run(zeit, String(token));
    if (r.changes !== 1) {
      db.exec('ROLLBACK');
      return { ok: false, grund: codeStatus(codeHolen(db, token)) };
    }
    const code = codeHolen(db, token);
    db.prepare(
      'INSERT INTO teilnahmen (token, vorname, nachname, email, telefon, lose, einwilligung_am) VALUES (?, ?, ?, ?, ?, ?, ?)'
    ).run(code.token, person.vorname, person.nachname, person.email, person.telefon, code.lose, zeit);
    db.exec('COMMIT');
    return { ok: true, lose: code.lose };
  } catch (e) {
    db.exec('ROLLBACK');
    throw e;
  }
}

// Fasst Teilnahmen je Person (E-Mail, ohne Groß-/Kleinschreibung) zusammen.
function personen(db) {
  const zeilen = db.prepare('SELECT * FROM teilnahmen ORDER BY id').all();
  const map = new Map();
  for (const z of zeilen) {
    const key = z.email.toLowerCase();
    const p = map.get(key);
    if (p) {
      p.lose += z.lose;
      // jüngste Angaben gewinnen
      Object.assign(p, { vorname: z.vorname, nachname: z.nachname, telefon: z.telefon });
    } else {
      map.set(key, { email: key, vorname: z.vorname, nachname: z.nachname, telefon: z.telefon, lose: z.lose });
    }
  }
  return [...map.values()];
}

// Zieht eine Person. Jedes Los hat dieselbe Chance; wer 5 Lose hat, liegt 5x im Topf.
// zufall(n) liefert eine gleichverteilte Ganzzahl in [0, n).
function ziehen(db, { preis = '', mehrfachgewinn = false } = {}, zufall = (n) => crypto.randomInt(n)) {
  let pool = personen(db);
  if (!mehrfachgewinn) {
    const schon = new Set(db.prepare('SELECT email FROM ziehungen').all().map((z) => z.email));
    pool = pool.filter((p) => !schon.has(p.email));
  }
  const summe = pool.reduce((s, p) => s + p.lose, 0);
  if (summe === 0) return null;
  let los = zufall(summe);
  let gewinner = pool[pool.length - 1];
  for (const p of pool) {
    if (los < p.lose) {
      gewinner = p;
      break;
    }
    los -= p.lose;
  }
  const zeit = jetzt();
  const r = db
    .prepare(
      'INSERT INTO ziehungen (email, vorname, nachname, telefon, lose, preis, pool_lose, pool_personen, gezogen_am) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'
    )
    .run(gewinner.email, gewinner.vorname, gewinner.nachname, gewinner.telefon, gewinner.lose, String(preis).slice(0, 200), summe, pool.length, zeit);
  return { id: Number(r.lastInsertRowid), ...gewinner, preis, pool_lose: summe, pool_personen: pool.length, gezogen_am: zeit };
}

function statistik(db) {
  const q = (sql) => db.prepare(sql).get();
  const stand = q(
    "SELECT COUNT(*) n, COALESCE(SUM(lose),0) lose, COALESCE(SUM(preis_cent),0) cent FROM codes WHERE quelle = 'stand' AND storniert = 0"
  );
  const offen = q('SELECT COUNT(*) n, COALESCE(SUM(lose),0) lose FROM codes WHERE storniert = 0 AND eingeloest_am IS NULL');
  const topf = q('SELECT COUNT(*) n, COALESCE(SUM(lose),0) lose FROM teilnahmen');
  const eingeloest = q('SELECT COALESCE(SUM(preis_cent),0) cent FROM codes WHERE eingeloest_am IS NOT NULL');
  return {
    stand_verkaeufe: stand.n,
    stand_lose: stand.lose,
    stand_umsatz_cent: stand.cent,
    offene_codes: offen.n,
    offene_lose: offen.lose,
    teilnahmen: topf.n,
    lose_im_topf: topf.lose,
    personen: personen(db).length,
    eingeloest_umsatz_cent: eingeloest.cent,
  };
}

module.exports = {
  PAKETE,
  oeffnen,
  codeAnlegen,
  codeHolen,
  codeStatus,
  codeStornieren,
  einloesen,
  personen,
  ziehen,
  statistik,
};
