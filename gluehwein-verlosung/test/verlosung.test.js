'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const D = require('../src/db');
const { erstelleApp, konfiguration } = require('../src/server');

const person = (n) => ({ vorname: `V${n}`, nachname: `N${n}`, email: `p${n}@example.at`, telefon: '+43 660 1234567' });

test('Code lässt sich genau einmal einlösen', () => {
  const db = D.oeffnen(':memory:');
  const t = D.codeAnlegen(db, 5, 'stand');
  assert.deepEqual(D.einloesen(db, t, person(1)), { ok: true, lose: 5 });
  assert.deepEqual(D.einloesen(db, t, person(2)), { ok: false, grund: 'eingeloest' });
  assert.equal(D.statistik(db).lose_im_topf, 5);
});

test('unbekannte und stornierte Codes werden abgelehnt', () => {
  const db = D.oeffnen(':memory:');
  assert.equal(D.einloesen(db, 'gibtsnicht', person(1)).grund, 'unbekannt');
  const t = D.codeAnlegen(db, 1, 'stand');
  assert.equal(D.codeStornieren(db, t), true);
  assert.equal(D.einloesen(db, t, person(1)).grund, 'storniert');
  assert.equal(D.statistik(db).teilnahmen, 0);
});

test('nur 1 oder 5 Lose möglich', () => {
  const db = D.oeffnen(':memory:');
  assert.throws(() => D.codeAnlegen(db, 3, 'stand'));
  assert.throws(() => D.codeAnlegen(db, 500, 'stand'));
});

test('jedes Los hat dieselbe Chance: 5 Lose = 5-fache Chance', () => {
  const db = D.oeffnen(':memory:');
  D.einloesen(db, D.codeAnlegen(db, 1, 'stand'), person(1));
  D.einloesen(db, D.codeAnlegen(db, 5, 'stand'), person(2));
  // Alle 6 Lospositionen einmal durchgehen
  const treffer = { 'p1@example.at': 0, 'p2@example.at': 0 };
  for (let i = 0; i < 6; i++) {
    const z = D.ziehen(db, { mehrfachgewinn: true }, (n) => { assert.equal(n, 6); return i; });
    treffer[z.email]++;
  }
  assert.deepEqual(treffer, { 'p1@example.at': 1, 'p2@example.at': 5 });
});

test('mehrere Käufe derselben Person zählen zusammen, Gewinner:innen fallen aus dem Topf', () => {
  const db = D.oeffnen(':memory:');
  D.einloesen(db, D.codeAnlegen(db, 1, 'stand'), person(1));
  D.einloesen(db, D.codeAnlegen(db, 5, 'druck', 'D01'), { ...person(1), email: 'P1@Example.at' });
  D.einloesen(db, D.codeAnlegen(db, 1, 'stand'), person(2));
  assert.equal(D.personen(db).find((p) => p.email === 'p1@example.at').lose, 6);
  const a = D.ziehen(db, {}, () => 0);
  assert.equal(a.email, 'p1@example.at');
  assert.equal(a.pool_lose, 7);
  const b = D.ziehen(db, {}, (n) => { assert.equal(n, 1); return 0; });
  assert.equal(b.email, 'p2@example.at');
  assert.equal(D.ziehen(db), null);
});

test('HTTP: Ablauf vom Verkauf bis zur Eintragung, Schutz der internen Bereiche', async (t) => {
  const cfg = konfiguration({ STAND_PIN: 'pin-123456', ADMIN_PASSWORD: 'admin-geheim', DB_FILE: ':memory:' });
  const db = D.oeffnen(':memory:');
  const server = erstelleApp(cfg, db).listen(0);
  t.after(() => server.close());
  const basis = `http://127.0.0.1:${server.address().port}`;
  const J = { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' };

  // ohne Anmeldung kein Code, keine Liste
  assert.equal((await fetch(`${basis}/api/stand/code`, { method: 'POST', headers: J, body: '{"lose":1}' })).status, 401);
  assert.equal((await fetch(`${basis}/api/admin/uebersicht`)).status, 401);
  assert.equal((await fetch(`${basis}/admin/export.csv`)).status, 401);

  const anmelden = async (rolle, pw) => {
    const r = await fetch(`${basis}/login`, { method: 'POST', body: new URLSearchParams({ rolle, pw }), redirect: 'manual' });
    return { status: r.status, cookie: (r.headers.get('set-cookie') || '').split(';')[0] };
  };
  assert.equal((await anmelden('stand', 'falsch')).status, 401);
  const stand = await anmelden('stand', 'pin-123456');
  assert.equal(stand.status, 303);
  // Stand-PIN öffnet die Verwaltung nicht
  assert.equal((await anmelden('admin', 'pin-123456')).status, 401);
  assert.equal((await fetch(`${basis}/api/admin/uebersicht`, { headers: { Cookie: stand.cookie } })).status, 401);

  const code = await (await fetch(`${basis}/api/stand/code`, { method: 'POST', headers: { ...J, Cookie: stand.cookie }, body: '{"lose":5}' })).json();
  assert.equal(code.status, 'offen');
  assert.match(code.svg, /^<svg/);
  assert.equal((await fetch(`${basis}/api/stand/code`, { method: 'POST', headers: { ...J, Cookie: stand.cookie }, body: '{"lose":50}' })).status, 400);

  assert.equal((await fetch(`${basis}/l/${code.token}`)).status, 200);
  const daten = { token: code.token, vorname: 'Anna', nachname: 'Muster', email: 'Anna@Example.at', telefon: '0660 1234567', einwilligung: true };
  const sende = (d) => fetch(`${basis}/api/einloesen`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) });
  assert.equal((await sende({ ...daten, einwilligung: false })).status, 400);
  assert.equal((await sende({ ...daten, email: 'keine-mail' })).status, 400);
  assert.equal((await fetch(`${basis}/l/${code.token}`)).status, 200, 'Fehlversuche verbrauchen den Code nicht');
  assert.deepEqual(await (await sende(daten)).json(), { ok: true, lose: 5 });
  assert.equal((await sende({ ...daten, email: 'zweite@example.at' })).status, 409);
  assert.equal((await fetch(`${basis}/l/${code.token}`)).status, 410);
  assert.equal((await fetch(`${basis}/l/erfunden`)).status, 404);

  const status = await (await fetch(`${basis}/api/stand/code/${code.token}`, { headers: { Cookie: stand.cookie } })).json();
  assert.equal(status.status, 'eingeloest');
  assert.equal(status.name, 'Anna M.');

  const admin = await anmelden('admin', 'admin-geheim');
  const u = await (await fetch(`${basis}/api/admin/uebersicht`, { headers: { Cookie: admin.cookie } })).json();
  assert.equal(u.statistik.lose_im_topf, 5);
  assert.equal(u.teilnahmen[0].email, 'anna@example.at');
  const csv = await (await fetch(`${basis}/admin/export.csv`, { headers: { Cookie: admin.cookie } })).text();
  assert.match(csv, /"Anna";"Muster";"anna@example.at";"0660 1234567";"5"/);
  const z = await (await fetch(`${basis}/api/admin/ziehen`, { method: 'POST', headers: { ...J, Cookie: admin.cookie }, body: '{"preis":"1. Preis"}' })).json();
  assert.equal(z.email, 'anna@example.at');
  // POST ohne X-Requested-With wird abgelehnt
  assert.equal((await fetch(`${basis}/api/admin/ziehen`, { method: 'POST', headers: { 'Content-Type': 'application/json', Cookie: admin.cookie }, body: '{}' })).status, 400);
});
