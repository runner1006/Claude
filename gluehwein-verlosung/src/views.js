'use strict';
// HTML-Seiten. Alle dynamischen Werte laufen durch esc().

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

const CSS = `
:root{--bg:#fbf6ee;--karte:#fff;--text:#2b1a14;--leise:#7a665c;--rot:#a3182b;--rot2:#7d1020;--gruen:#1f6b3a;--rand:#e6d9c8;--warn:#b25c00}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:17px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:34rem;margin:0 auto;padding:20px 16px 48px}
main.breit{max-width:64rem}
h1{font-size:1.6rem;line-height:1.2;margin:.2em 0 .4em}
h2{font-size:1.15rem;margin:1.6em 0 .5em}
p{margin:.5em 0}
.leise{color:var(--leise);font-size:.92rem}
.karte{background:var(--karte);border:1px solid var(--rand);border-radius:14px;padding:18px;margin:14px 0}
label{display:block;font-weight:600;margin:14px 0 4px}
input[type=text],input[type=email],input[type=tel],input[type=password],input[type=number]{width:100%;font:inherit;padding:13px 12px;border:1.5px solid #cdbba6;border-radius:10px;background:#fff;color:inherit}
input:focus{outline:3px solid #e9b9c0;border-color:var(--rot)}
.haken{display:flex;gap:12px;align-items:flex-start;font-weight:400;margin-top:18px}
.haken input{width:26px;height:26px;flex:none;margin-top:1px;accent-color:var(--rot)}
button,.knopf{font:inherit;font-weight:700;border:0;border-radius:12px;padding:15px 18px;background:var(--rot);color:#fff;cursor:pointer;width:100%;margin-top:18px;display:inline-block;text-align:center;text-decoration:none}
button:active{background:var(--rot2)}
button:disabled{opacity:.55;cursor:default}
button.zweit{background:#fff;color:var(--rot);border:1.5px solid var(--rot)}
button.klein{width:auto;padding:8px 12px;margin:0;font-size:.9rem}
.fehler{color:var(--rot);font-weight:600;margin-top:12px;min-height:1.2em}
.ok{color:var(--gruen)}
.gross{font-size:3.2rem;line-height:1;margin:.2em 0}
.mitte{text-align:center}
.wahl{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.wahl button{margin:0;padding:26px 8px;font-size:1.25rem}
.wahl small{display:block;font-weight:400;opacity:.9}
.qr{background:#fff;padding:10px;border-radius:12px;max-width:21rem;margin:10px auto}
.qr svg{display:block;width:100%;height:auto}
table{border-collapse:collapse;width:100%;font-size:.92rem}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--rand);vertical-align:top}
.rollen{overflow-x:auto}
.kacheln{display:grid;grid-template-columns:repeat(auto-fit,minmax(9rem,1fr));gap:10px}
.kachel{background:var(--karte);border:1px solid var(--rand);border-radius:12px;padding:12px}
.kachel b{display:block;font-size:1.6rem}
.reihe{display:flex;gap:10px;flex-wrap:wrap;align-items:end}
.reihe>*{flex:1 1 9rem}
.gewinner{font-size:2.2rem;font-weight:800;line-height:1.15;margin:.3em 0}
a{color:var(--rot)}
.marke{font-weight:800;color:var(--rot);letter-spacing:.02em}
@media print{
  body{background:#fff} .nichtdrucken{display:none!important} main{max-width:none;padding:0}
}
.bogen{display:grid;grid-template-columns:repeat(3,1fr);gap:0}
.los{border:1px dashed #999;padding:10px 10px 12px;text-align:center;break-inside:avoid;page-break-inside:avoid}
.los svg{width:70%;height:auto;display:block;margin:4px auto}
.los b{font-size:1.1rem}
.los small{display:block;font-size:.72rem;color:#444}
`;

function seite(titel, inhalt, { breit = false, script = '' } = {}) {
  return `<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>${esc(titel)}</title>
<style>${CSS}</style>
</head>
<body>
<main${breit ? ' class="breit"' : ''}>
${inhalt}
</main>
${script ? `<script>${script}</script>` : ''}
</body>
</html>`;
}

function start(cfg) {
  return seite(
    'Glühwein-Verlosung',
    `<p class="marke">${esc(cfg.veranstalter)}</p>
<h1>Glühwein-Verlosung</h1>
<div class="karte">
<p>Lose gibt es direkt bei uns am Stand: <b>1 Los um € 5,–</b> oder <b>5 Lose um € 20,–</b>.</p>
<p>Nach dem Kauf bekommst du einen QR-Code. Damit trägst du dich in wenigen Sekunden für die Verlosung ein.</p>
</div>
<p class="leise"><a href="/datenschutz">Datenschutz</a></p>`
  );
}

function hinweis(titel, text, cfg) {
  return seite(
    titel,
    `<p class="marke">${esc(cfg.veranstalter)}</p>
<h1>${esc(titel)}</h1>
<div class="karte"><p>${esc(text)}</p></div>
<p class="leise"><a href="/datenschutz">Datenschutz</a></p>`
  );
}

function formular(code, cfg) {
  const lose = code.lose === 1 ? '1 Los' : `${code.lose} Lose`;
  const mal = code.lose === 1 ? 'einmal' : `${code.lose}-mal`;
  return seite(
    'Für die Verlosung eintragen',
    `<p class="marke">${esc(cfg.veranstalter)}</p>
<div id="eingabe">
<h1>Danke für deinen Kauf!</h1>
<p>Du hast <b>${lose}</b> und nimmst damit <b>${mal}</b> an der Verlosung teil. Trag dich noch kurz ein, damit wir dich im Gewinnfall erreichen.</p>
<form id="f" class="karte" novalidate>
  <label for="vorname">Vorname</label>
  <input id="vorname" name="vorname" type="text" autocomplete="given-name" autocapitalize="words" maxlength="80" required>
  <label for="nachname">Nachname</label>
  <input id="nachname" name="nachname" type="text" autocomplete="family-name" autocapitalize="words" maxlength="80" required>
  <label for="email">E-Mail-Adresse</label>
  <input id="email" name="email" type="email" autocomplete="email" inputmode="email" autocapitalize="none" spellcheck="false" maxlength="160" required>
  <label for="telefon">Telefonnummer</label>
  <input id="telefon" name="telefon" type="tel" autocomplete="tel" inputmode="tel" maxlength="30" required>
  <label class="haken" for="einwilligung">
    <input id="einwilligung" name="einwilligung" type="checkbox" required>
    <span>Ich habe die <a href="/datenschutz" target="_blank" rel="noopener">Datenschutzerklärung</a> gelesen und bin einverstanden, dass meine Daten für die Durchführung der Verlosung verwendet werden.</span>
  </label>
  <div class="fehler" id="fehler" role="alert"></div>
  <button id="senden" type="submit">Jetzt teilnehmen</button>
</form>
<p class="leise">Dieser Code gilt genau einmal. Nach dem Absenden ist er verbraucht.</p>
</div>
<div id="fertig" class="karte mitte" hidden>
  <p class="gross">🎉</p>
  <h1>Du bist dabei!</h1>
  <p id="fertigtext"></p>
  <p class="leise">Die Gewinner:innen werden am letzten Tag des Standbetriebs gezogen und von uns verständigt. Viel Glück!</p>
</div>`,
    {
      script: `
var f=document.getElementById('f'),fehler=document.getElementById('fehler'),knopf=document.getElementById('senden');
f.addEventListener('submit',function(e){
  e.preventDefault();
  fehler.textContent='';
  var d={token:${JSON.stringify(code.token)},vorname:f.vorname.value,nachname:f.nachname.value,email:f.email.value,telefon:f.telefon.value,einwilligung:f.einwilligung.checked};
  knopf.disabled=true;knopf.textContent='Wird gesendet …';
  fetch('/api/einloesen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)})
  .then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j}})})
  .then(function(x){
    if(x.ok){
      document.getElementById('eingabe').hidden=true;
      document.getElementById('fertigtext').textContent=x.j.lose===1?'Dein Los ist im Topf.':'Deine '+x.j.lose+' Lose sind im Topf.';
      document.getElementById('fertig').hidden=false;window.scrollTo(0,0);
    }else{
      fehler.textContent=x.j.fehler||'Das hat leider nicht geklappt.';
      if(x.j.feld&&f[x.j.feld])f[x.j.feld].focus();
      knopf.disabled=false;knopf.textContent='Jetzt teilnehmen';
    }
  }).catch(function(){
    fehler.textContent='Keine Verbindung. Bitte noch einmal versuchen.';
    knopf.disabled=false;knopf.textContent='Jetzt teilnehmen';
  });
});`,
    }
  );
}

function datenschutz(cfg) {
  return seite(
    'Datenschutzerklärung',
    `<p class="marke">${esc(cfg.veranstalter)}</p>
<h1>Datenschutzerklärung zur Verlosung</h1>
<div class="karte">
<h2 style="margin-top:0">Verantwortlich</h2>
<p>${esc(cfg.veranstalter)}<br>Kontakt: <a href="mailto:${esc(cfg.kontakt)}">${esc(cfg.kontakt)}</a></p>
<h2>Welche Daten wir erheben</h2>
<p>Vorname, Nachname, E-Mail-Adresse, Telefonnummer, die Anzahl deiner Lose sowie den Zeitpunkt deiner Eintragung und Einwilligung.</p>
<h2>Wofür wir die Daten verwenden</h2>
<p>Ausschließlich zur Durchführung der Verlosung: zur Ziehung der Gewinner:innen und um dich im Gewinnfall zu verständigen. Rechtsgrundlage ist deine Einwilligung (Art. 6 Abs. 1 lit. a DSGVO) bzw. die Durchführung der Verlosung (Art. 6 Abs. 1 lit. b DSGVO).</p>
<h2>Weitergabe</h2>
<p>Wir geben deine Daten nicht an Dritte weiter und verwenden sie nicht für Werbung. Für den Betrieb dieser Seite nutzen wir einen technischen Dienstleister (Hosting).</p>
<h2>Speicherdauer</h2>
<p>Wir löschen alle Daten spätestens vier Wochen nach der Ziehung und der Übergabe der Gewinne.</p>
<h2>Deine Rechte</h2>
<p>Du kannst jederzeit Auskunft, Berichtigung oder Löschung verlangen und deine Einwilligung widerrufen (dann nimmst du nicht mehr an der Verlosung teil). Schreib uns dazu an die oben genannte Adresse. Außerdem hast du das Recht auf Beschwerde bei der Österreichischen Datenschutzbehörde (dsb.gv.at).</p>
</div>`
  );
}

function login(rolle, fehler) {
  const stand = rolle === 'stand';
  return seite(
    stand ? 'Stand – Anmeldung' : 'Verwaltung – Anmeldung',
    `<h1>${stand ? 'Stand' : 'Verwaltung'}</h1>
<form class="karte" method="post" action="/login">
  <input type="hidden" name="rolle" value="${stand ? 'stand' : 'admin'}">
  <label for="pw">${stand ? 'Stand-PIN' : 'Passwort'}</label>
  <input id="pw" name="pw" type="password" autocomplete="current-password" autofocus required>
  <div class="fehler">${esc(fehler || '')}</div>
  <button type="submit">Anmelden</button>
</form>`
  );
}

function stand() {
  return seite(
    'Stand – Lose verkaufen',
    `<div id="wahl">
<h1>Neuer Verkauf</h1>
<p class="leise">Erst kassieren, dann antippen. Der QR-Code gilt genau einmal.</p>
<div class="wahl">
  <button data-lose="1">1 Los<small>€ 5,–</small></button>
  <button data-lose="5">5 Lose<small>€ 20,–</small></button>
</div>
<div class="fehler" id="fehler"></div>
<h2>Letzte Verkäufe</h2>
<div class="rollen"><table id="liste"><tbody></tbody></table></div>
<p class="leise" id="summe"></p>
</div>
<div id="zeigen" class="mitte" hidden>
  <h1 id="ztitel"></h1>
  <div id="qrbox">
    <p>Kund:in scannt den Code mit der Handykamera.</p>
    <div class="qr" id="qr"></div>
    <p class="leise">Wartet auf Eintragung …</p>
  </div>
  <div id="erledigt" hidden>
    <p class="gross ok">✓</p>
    <p id="wer" style="font-size:1.3rem;font-weight:700"></p>
  </div>
  <button id="weiter">Nächster Verkauf</button>
  <button id="storno" class="zweit">Vertippt – Code stornieren</button>
</div>`,
    {
      script: `
var aktiv=null,timer=null;
function api(m,u,b){return fetch(u,{method:m,headers:{'Content-Type':'application/json','X-Requested-With':'fetch'},body:b?JSON.stringify(b):undefined}).then(function(r){if(r.status===401){location.reload();throw 0}return r.json()})}
function el(t,txt){var e=document.createElement(t);if(txt!=null)e.textContent=txt;return e}
function zeit(s){return new Date(s).toLocaleTimeString('de-AT',{hour:'2-digit',minute:'2-digit'})}
function liste(){
  api('GET','/api/stand/codes').then(function(j){
    var tb=document.querySelector('#liste tbody');tb.textContent='';
    j.codes.forEach(function(c){
      var tr=el('tr');
      tr.appendChild(el('td',zeit(c.erstellt)));
      tr.appendChild(el('td',c.lose===1?'1 Los':c.lose+' Lose'));
      var s=el('td',c.status==='eingeloest'?'✓ '+(c.name||'eingetragen'):c.status==='storniert'?'storniert':'offen');
      if(c.status==='eingeloest')s.className='ok';
      tr.appendChild(s);
      var td=el('td');
      if(c.status==='offen'){var b=el('button','QR zeigen');b.className='klein zweit';b.onclick=function(){oeffne(c.token)};td.appendChild(b)}
      tr.appendChild(td);tb.appendChild(tr);
    });
    document.getElementById('summe').textContent='Heute: '+j.heute.verkaeufe+' Verkäufe, '+j.heute.lose+' Lose, € '+(j.heute.cent/100).toFixed(2).replace('.',',');
  }).catch(function(){});
}
function zeige(c){
  aktiv=c.token;
  document.getElementById('wahl').hidden=true;document.getElementById('zeigen').hidden=false;
  document.getElementById('ztitel').textContent=c.lose===1?'1 Los':c.lose+' Lose';
  var fertig=c.status==='eingeloest';
  document.getElementById('qrbox').hidden=fertig;document.getElementById('erledigt').hidden=!fertig;
  document.getElementById('storno').hidden=c.status!=='offen';
  if(c.svg)document.getElementById('qr').innerHTML=c.svg;
  if(fertig)document.getElementById('wer').textContent='Eingetragen: '+(c.name||'');
  clearTimeout(timer);
  if(c.status==='offen')timer=setTimeout(function(){if(aktiv===c.token)oeffne(c.token,true)},2000);
}
function oeffne(t,still){api('GET','/api/stand/code/'+encodeURIComponent(t)+(still?'?ohneqr=1':'')).then(zeige).catch(function(){if(aktiv===t)timer=setTimeout(function(){oeffne(t,true)},3000)})}
function zurueck(){aktiv=null;clearTimeout(timer);document.getElementById('zeigen').hidden=true;document.getElementById('wahl').hidden=false;liste()}
document.querySelectorAll('.wahl button').forEach(function(b){b.onclick=function(){
  document.getElementById('fehler').textContent='';
  api('POST','/api/stand/code',{lose:Number(b.dataset.lose)}).then(function(c){if(c.fehler){document.getElementById('fehler').textContent=c.fehler}else zeige(c)}).catch(function(){document.getElementById('fehler').textContent='Keine Verbindung.'});
}});
document.getElementById('weiter').onclick=zurueck;
document.getElementById('storno').onclick=function(){if(confirm('Code wirklich stornieren?'))api('POST','/api/stand/storno',{token:aktiv}).then(zurueck)};
liste();`,
    }
  );
}

function admin() {
  return seite(
    'Verwaltung – Verlosung',
    `<h1>Verwaltung</h1>
<div class="kacheln" id="kacheln"></div>

<h2>Ziehung</h2>
<div class="karte">
  <div class="reihe">
    <div><label for="preis" style="margin-top:0">Preis (optional)</label><input id="preis" type="text" maxlength="200" placeholder="z. B. 1. Preis: Gutschein"></div>
  </div>
  <label class="haken" for="mehrfach"><input id="mehrfach" type="checkbox"><span>Dieselbe Person darf mehrmals gewinnen</span></label>
  <button id="ziehen">Gewinner:in ziehen</button>
  <div id="ergebnis" class="mitte" hidden>
    <p class="leise" id="epreis"></p>
    <p class="gewinner" id="ename"></p>
    <p class="leise" id="epool"></p>
    <button class="klein zweit" id="ekontaktknopf">Kontaktdaten anzeigen</button>
    <p id="ekontakt" hidden></p>
  </div>
  <div class="fehler" id="zfehler"></div>
</div>
<div class="rollen"><table id="ziehungen"><thead><tr><th>#</th><th>Zeit</th><th>Preis</th><th>Name</th><th>E-Mail</th><th>Telefon</th><th>Lose</th></tr></thead><tbody></tbody></table></div>
<p><button class="klein zweit" id="zreset">Alle Ziehungen zurücksetzen (z. B. nach Probelauf)</button></p>

<h2>Teilnehmer:innen</h2>
<p><a class="knopf" style="width:auto;margin:0" href="/admin/export.csv">Als CSV herunterladen</a></p>
<div class="rollen"><table id="tn"><thead><tr><th>Zeit</th><th>Vorname</th><th>Nachname</th><th>E-Mail</th><th>Telefon</th><th>Lose</th></tr></thead><tbody></tbody></table></div>

<h2>Lose zum Ausdrucken</h2>
<div class="karte">
  <p class="leise" style="margin-top:0">Alternative zum Live-QR am Handy: Kärtchen mit Einmal-Codes vorab drucken und beim Kauf aushändigen. Die Bögen wie Bargeld behandeln – jedes Kärtchen ist ein bezahltes Los.</p>
  <div class="reihe">
    <div><label for="d1" style="margin-top:0">Kärtchen „1 Los“</label><input id="d1" type="number" min="0" max="500" value="30"></div>
    <div><label for="d5" style="margin-top:0">Kärtchen „5 Lose“</label><input id="d5" type="number" min="0" max="500" value="12"></div>
  </div>
  <button id="drucken" class="zweit">Druckbogen erzeugen</button>
  <div id="chargen"></div>
</div>

<h2>Daten löschen</h2>
<div class="karte">
  <p class="leise" style="margin-top:0">Nach Abschluss der Verlosung alle personenbezogenen Daten löschen. Vorher die CSV sichern, falls noch Gewinne zu übergeben sind. Das lässt sich nicht rückgängig machen.</p>
  <button id="loeschen" class="zweit">Alle Daten endgültig löschen …</button>
</div>`,
    {
      breit: true,
      script: `
function api(m,u,b){return fetch(u,{method:m,headers:{'Content-Type':'application/json','X-Requested-With':'fetch'},body:b?JSON.stringify(b):undefined}).then(function(r){if(r.status===401){location.reload();throw 0}return r.json()})}
function el(t,txt){var e=document.createElement(t);if(txt!=null)e.textContent=txt;return e}
function zeit(s){return new Date(s).toLocaleString('de-AT',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}
function euro(c){return '€ '+(c/100).toFixed(2).replace('.',',')}
function zeile(tb,werte){var tr=el('tr');werte.forEach(function(w){tr.appendChild(el('td',w))});tb.appendChild(tr)}
function laden(){
  api('GET','/api/admin/uebersicht').then(function(j){
    var s=j.statistik,k=document.getElementById('kacheln');k.textContent='';
    [[s.lose_im_topf,'Lose im Topf'],[s.personen,'Personen'],[s.stand_lose,'Lose am Stand verkauft'],[euro(s.stand_umsatz_cent),'Umsatz Stand (Live-Codes)'],[s.offene_codes,'Codes noch nicht eingelöst']].forEach(function(x){var d=el('div');d.className='kachel';d.appendChild(el('b',x[0]));d.appendChild(el('span',x[1]));k.appendChild(d)});
    var tb=document.querySelector('#tn tbody');tb.textContent='';
    j.teilnahmen.forEach(function(t){zeile(tb,[zeit(t.einwilligung_am),t.vorname,t.nachname,t.email,t.telefon,t.lose])});
    var zb=document.querySelector('#ziehungen tbody');zb.textContent='';
    j.ziehungen.forEach(function(z,i){zeile(zb,[i+1,zeit(z.gezogen_am),z.preis,z.vorname+' '+z.nachname,z.email,z.telefon,z.lose])});
    var c=document.getElementById('chargen');c.textContent='';
    j.chargen.forEach(function(ch){var p=el('p');var a=el('a','Druckbogen '+ch.charge+' öffnen');a.href='/admin/druck/'+encodeURIComponent(ch.charge);a.target='_blank';p.appendChild(a);p.appendChild(document.createTextNode(' – '+ch.codes+' Kärtchen, davon '+ch.eingeloest+' eingelöst'));c.appendChild(p)});
  });
}
document.getElementById('ziehen').onclick=function(){
  var f=document.getElementById('zfehler');f.textContent='';
  api('POST','/api/admin/ziehen',{preis:document.getElementById('preis').value,mehrfachgewinn:document.getElementById('mehrfach').checked}).then(function(z){
    if(z.fehler){f.textContent=z.fehler;return}
    document.getElementById('ergebnis').hidden=false;
    document.getElementById('epreis').textContent=z.preis||'';
    document.getElementById('ename').textContent=z.vorname+' '+z.nachname.charAt(0)+'.';
    document.getElementById('epool').textContent='gezogen aus '+z.pool_lose+' Losen von '+z.pool_personen+' Personen';
    var k=document.getElementById('ekontakt');k.hidden=true;k.textContent=z.vorname+' '+z.nachname+' · '+z.email+' · '+z.telefon+' · '+z.lose+(z.lose===1?' Los':' Lose');
    document.getElementById('preis').value='';
    laden();
  });
};
document.getElementById('ekontaktknopf').onclick=function(){var k=document.getElementById('ekontakt');k.hidden=!k.hidden};
document.getElementById('zreset').onclick=function(){if(confirm('Alle bisherigen Ziehungen verwerfen? Die Teilnehmer:innen bleiben erhalten.'))api('POST','/api/admin/ziehungen-zuruecksetzen',{}).then(function(){document.getElementById('ergebnis').hidden=true;laden()})};
document.getElementById('drucken').onclick=function(){api('POST','/api/admin/druckcharge',{einzel:Number(document.getElementById('d1').value),buendel:Number(document.getElementById('d5').value)}).then(function(j){if(j.fehler)alert(j.fehler);else{laden();window.open('/admin/druck/'+encodeURIComponent(j.charge),'_blank')}})};
document.getElementById('loeschen').onclick=function(){var w=prompt('Wirklich ALLE Codes, Teilnahmen und Ziehungen löschen? Zum Bestätigen LÖSCHEN eintippen.');if(w==='LÖSCHEN')api('POST','/api/admin/alles-loeschen',{bestaetigung:w}).then(laden)};
laden();setInterval(laden,15000);`,
    }
  );
}

function druckbogen(charge, karten, cfg) {
  const k = karten
    .map(
      (c) => `<div class="los">
<b>${c.lose === 1 ? '1 Los' : `${c.lose} Lose`}</b>
${c.svg}
<small>${esc(cfg.veranstalter)} · Glühwein-Verlosung</small>
<small>QR-Code scannen und eintragen. Gilt genau einmal.</small>
</div>`
    )
    .join('\n');
  return seite(
    `Druckbogen ${charge}`,
    `<div class="nichtdrucken"><h1>Druckbogen ${esc(charge)}</h1>
<p class="leise">Nur noch nicht eingelöste Kärtchen. Auf A4 drucken und entlang der Linien schneiden.</p>
<p><button class="klein" onclick="print()">Drucken</button></p></div>
<div class="bogen">${k}</div>`,
    { breit: true }
  );
}

module.exports = { esc, start, hinweis, formular, datenschutz, login, stand, admin, druckbogen };
