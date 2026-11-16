/*
 * HistogramRange — wiederverwendbarer Dual-Slider mit Dichte-Histogramm.
 * Kein Framework, keine Abhängigkeiten. Eigenständig einbindbar via:
 *     <script src="histogram-range.js"></script>
 *     const hr = HistogramRange({ values:[...], onChange:([lo,hi])=>... });
 *     container.append(hr.element);
 *
 * Optionen:
 *   values   : number[]  – Verteilung, die als Histogramm gebinnt wird
 *   min,max  : number    – Domain (Default: aus values)
 *   step     : number    – Raster (Default 1)
 *   bins     : number    – Anzahl Histogramm-Balken (Default 32)
 *   scale    : "linear" | "auto" (auch "log") | "quantile"
 *              "auto"     => Achse nach der Schiefe der Verteilung: rechtsschief (Schiefe > 1, z. B. Tore)
 *                            logarithmisch, sonst linear.
 *              "quantile" => nicht-lineare Achse: dort wo mehr Werte liegen,
 *              ist die Achse dichter (mehr Platz / feinere Kontrolle).
 *   zero     : bool      – Nullspitze getrennt behandeln (Default true): liegen >= 15 % der Werte genau auf dem
 *              Minimum (z. B. 0 Minuten), bekommt diese Punktmasse einen eigenen, schraffierten Balken links
 *              und zaehlt nicht in die Skalierung der uebrigen Balken (zero-inflated Verteilung).
 *   zeroNote : (n0, anteil, text) => string – Hinweiszeile zur Nullspitze (i18n durch den Aufrufer)
 *
 * Balkenhoehen (ausser "quantile"): Wurzel der Dichte (Rootogramm nach Tukey) – stabilisiert die Varianz von
 * Zaehlwerten, sodass duenn besetzte Bereiche neben einem Gipfel sichtbar bleiben. Bins haben variable Breite
 * (an das Raster "step" gesnappt, keine leeren Zwischen-Bins bei ganzzahligen Werten); Flaeche ~ Anzahl.
 *   format   : v=>string – Anzeige der Werte (Default gerundet)
 *   inputs   : bool      – manuelle Min/Max-Eingabefelder (Default true)
 *   title    : string    – optionaler Titel; avg: optionaler HTML-Text rechts
 *   onChange : ([lo,hi]) – nach dem Ziehen; lo/hi sind '' am Domain-Rand
 *   onInput  : ([lo,hi]) – live während des Ziehens (numerisch)
 *
 * Rückgabe: { element, getRange, setRange(lo,hi), reset() }
 * getRange/onChange liefern '' für einen offenen Rand (= kein Filter).
 */
(function (global) {
  "use strict";

  var STYLE_ID = "histogram-range-css";
  var CSS = "" +
    ".hr{--hr-acc:var(--accent,#34B190);--hr-mut:var(--line,#2a313d);--hr-txt:var(--muted,#9aa4b2);width:100%;user-select:none}" +
    ".hr-top{display:flex;justify-content:space-between;align-items:baseline;font-size:12px;color:var(--hr-txt);margin-bottom:6px}" +
    ".hr-top b{color:var(--text,#e6e9ef);font-weight:600}" +
    ".hr-histo{display:flex;align-items:flex-end;gap:1px;height:42px;margin:0 8px 5px}" +
    ".hr-bar{flex:1 1 0;background:var(--hr-mut);border-radius:2px 2px 0 0;min-height:2px;transition:background .08s}" +
    ".hr-bar.on{background:var(--hr-acc)}" +
    ".hr-zero{margin-right:3px;opacity:.9;background:repeating-linear-gradient(135deg,var(--hr-mut) 0 3px,transparent 3px 6px);border:1px solid var(--hr-mut);border-bottom:0}" +
    ".hr-zero.on{background:repeating-linear-gradient(135deg,var(--hr-acc) 0 3px,transparent 3px 6px);border-color:var(--hr-acc)}" +
    ".hr-note{font-size:11px;line-height:1.35;color:var(--hr-txt);margin:0 8px 7px}" +
    ".hr-track{position:relative;height:22px;margin:0 8px;touch-action:none}" +
    ".hr-rail{position:absolute;left:0;right:0;top:50%;height:5px;transform:translateY(-50%);background:var(--hr-mut);border-radius:3px}" +
    ".hr-fill{position:absolute;top:50%;height:5px;transform:translateY(-50%);background:var(--hr-acc);border-radius:3px}" +
    ".hr-thumb{position:absolute;top:50%;width:16px;height:16px;border-radius:50%;background:#fff;border:2px solid var(--hr-acc);" +
      "transform:translate(-50%,-50%);cursor:grab;box-shadow:0 1px 4px rgba(0,0,0,.45);z-index:2}" +
    ".hr-thumb:active{cursor:grabbing}" +
    ".hr-bubble{position:absolute;top:50%;left:50%;transform:translate(-50%,14px);background:#0b0d11;color:#fff;font-size:11px;" +
      "font-weight:600;padding:1px 7px;border-radius:20px;white-space:nowrap;pointer-events:none;font-variant-numeric:tabular-nums}" +
    ".hr-vals{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin:5px 8px 0;font-size:12px;font-variant-numeric:tabular-nums;color:var(--hr-txt)}" +
    ".hr-val{white-space:nowrap;font-weight:600}.hr-val.set{color:var(--hr-acc)}.hr-val-sep{flex:1;text-align:center;opacity:.5}" +
    ".hr-inputs{display:flex;align-items:center;gap:7px;margin:7px 8px 0}" +
    ".hr-inputs input{flex:1 1 0;width:100%;min-width:0;background:var(--panel2,#1f242e);border:1px solid var(--line,#2a313d);" +
      "color:var(--text,#e6e9ef);padding:7px 9px;border-radius:8px;font-size:12px;font-variant-numeric:tabular-nums}" +
    ".hr-inputs input:focus{outline:none;border-color:var(--hr-acc)}" +
    ".hr-inputs span{color:var(--hr-txt);font-size:12px}";

  function injectCSS() {
    if (document.getElementById(STYLE_ID)) return;
    var s = document.createElement("style");
    s.id = STYLE_ID; s.textContent = CSS;
    document.head.appendChild(s);
  }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
  function elem(cls, parent) { var d = document.createElement("div"); if (cls) d.className = cls; if (parent) parent.appendChild(d); return d; }

  function HistogramRange(opts) {
    opts = opts || {};
    injectCSS();
    var values = (opts.values || []).map(Number).filter(function (v) { return !isNaN(v); }).sort(function (a, b) { return a - b; });
    var n = values.length;
    var dmin = opts.min != null ? opts.min : (n ? values[0] : 0);
    var dmax = opts.max != null ? opts.max : (n ? values[n - 1] : 100);
    if (dmax <= dmin) dmax = dmin + 1;
    var step = opts.step || 1;
    var bins = opts.bins || 32;
    var fmt = opts.format || function (v) { return String(Math.round(v)); };
    var mode = (opts.scale === "quantile" && n > 1) ? "quantile"
             : ((opts.scale === "log" || opts.scale === "auto") ? "auto" : "linear");
    var showHisto = opts.histo !== false;   // false => nur Slider (z.B. gleichverteilte Perzentile)
    var withInputs = opts.inputs !== false;
    var lo = dmin, hi = dmax;

    // ---- Nullspitze (zero-inflated): Punktmasse auf dem Minimum getrennt behandeln ----
    var n0 = 0; while (n0 < n && values[n0] === dmin) n0++;
    var zeroMode = mode !== "quantile" && opts.zero !== false && n > 0 && n0 < n && n0 / n >= 0.15;
    var v0 = zeroMode ? values[n0] : dmin;          // kleinster Wert ueber dem Minimum
    var Z = zeroMode ? 0.07 : 0;                    // Anteil der Achse fuer die Punktmasse
    // ---- Achse fuer den stetigen Teil: Schiefe entscheidet zwischen linear und log ----
    var useLog = false, span = dmax - v0; if (!(span > 0)) span = 1;
    if (mode === "auto") {
      var m1 = 0, cnt = n - (zeroMode ? n0 : 0), k0 = zeroMode ? n0 : 0, q;
      for (q = k0; q < n; q++) m1 += values[q]; m1 /= Math.max(cnt, 1);
      var m2 = 0, m3 = 0, dq;
      for (q = k0; q < n; q++) { dq = values[q] - m1; m2 += dq * dq; m3 += dq * dq * dq; }
      m2 /= Math.max(cnt, 1); m3 /= Math.max(cnt, 1);
      var skew = m2 > 0 ? m3 / Math.pow(m2, 1.5) : 0;
      useLog = skew > 1 && span > 20 * step;
    }
    var logMax = Math.log(span + 1);
    function g(v) { return clamp(useLog ? Math.log(Math.max(v - v0, 0) + 1) / logMax : (v - v0) / span, 0, 1); }
    function gi(p) { p = clamp(p, 0, 1); return useLog ? v0 + Math.exp(p * logMax) - 1 : v0 + p * span; }

    // ---- Achsen-Mapping Position<->Wert ----
    function toPos(v) {
      if (mode !== "quantile") {
        if (!zeroMode) return g(v);
        if (v <= dmin) return 0;
        if (v < v0) return Z;
        return Z + (1 - Z) * g(v);
      }
      if (v <= values[0]) return 0;
      if (v >= values[n - 1]) return 1;
      var a = 0, b = n;
      while (a < b) { var m = (a + b) >> 1; if (values[m] < v) a = m + 1; else b = m; }
      var up = a; while (up < n && values[up] === v) up++;
      return (a + up) / 2 / n;
    }
    function toVal(p) {
      p = clamp(p, 0, 1);
      if (mode !== "quantile") {
        if (!zeroMode) return gi(p);
        if (p < Z * 0.5) return dmin;               // ganz links: Nullen eingeschlossen
        if (p <= Z) return v0;                      // knapp daneben: ab dem kleinsten Wert > Minimum
        return gi((p - Z) / (1 - Z));
      }
      var idx = p * (n - 1), i = Math.floor(idx), f = idx - i;
      return values[i] + ((values[Math.min(i + 1, n - 1)]) - values[i]) * f;
    }

    // ---- Histogramm-Bins ----
    var dens = [], centers = [], flexes = [], i, j;
    if (mode === "quantile") {                      // Dichte je Wert-Einheit im Positionsraum (wie bisher)
      for (i = 0; i < bins; i++) {
        var vLo = toVal(i / bins), vHi = toVal((i + 1) / bins);
        if (vHi <= vLo) vHi = vLo + step;
        var c = 0, last = (i === bins - 1);
        for (j = 0; j < n; j++) { var x = values[j]; if (x >= vLo && (x < vHi || (last && x <= vHi))) c++; }
        dens.push(c / Math.max(vHi - vLo, step)); centers.push((vLo + vHi) / 2); flexes.push(1);
      }
    } else {
      // Kanten im transformierten Raum gleichmaessig, dann ans Raster gesnappt und dedupliziert
      var edges = [v0], e;
      for (i = 1; i <= bins; i++) { e = Math.round(gi(i / bins) / step) * step; if (e > edges[edges.length - 1] + step * 1e-6) edges.push(e); }
      if (edges[edges.length - 1] < dmax) edges.push(dmax); else edges[edges.length - 1] = dmax;
      if (edges.length < 2) edges.push(dmax + step);
      var ptr = zeroMode ? n0 : 0;
      for (i = 0; i < edges.length - 1; i++) {
        var a2 = edges[i], b2 = edges[i + 1], lastB = (i === edges.length - 2), c2 = 0;
        while (ptr < n && (values[ptr] < b2 || (lastB && values[ptr] <= b2))) { if (values[ptr] >= a2) c2++; ptr++; }
        var w = Math.max(g(b2) - g(a2), 1e-6);
        dens.push(Math.sqrt(c2 / w));               // Rootogramm: Wurzel der Dichte
        centers.push((a2 + b2) / 2); flexes.push(w);
      }
    }
    var maxDens = Math.max.apply(null, dens.concat([1e-9]));

    // ---- DOM ----
    var root = elem("hr");
    if (opts.title != null) {
      var top = elem("hr-top", root);
      var ts = document.createElement("span"); ts.textContent = opts.title; top.appendChild(ts);
      if (opts.avg != null) { var as = document.createElement("span"); as.innerHTML = opts.avg; top.appendChild(as); }
    }
    var bars = [];
    if (showHisto) {
      if (zeroMode && opts.zeroNote) { var note = elem("hr-note", root); note.textContent = opts.zeroNote(n0, n0 / n, fmt(dmin)); }
      var histo = elem("hr-histo", root);
      if (zeroMode) {                               // Punktmasse: eigener, schraffierter Balken (nicht massstaeblich)
        var zb = elem("hr-bar hr-zero", histo); zb.style.height = "100%"; zb.style.flex = (Z / (1 - Z)) + " 1 0";
        zb.title = fmt(dmin) + ": " + n0 + " (" + Math.round(n0 / n * 100) + " %)";
        bars.push(zb);
      }
      dens.forEach(function (dv, k) { var b = elem("hr-bar", histo); b.style.height = (dv / maxDens * 100) + "%";
        b.style.flex = flexes[k] + " 1 0"; bars.push(b); });
      if (zeroMode) centers = [dmin].concat(centers);
    }
    var track = elem("hr-track", root);
    elem("hr-rail", track);
    var fill = elem("hr-fill", track);
    var thumbLo = elem("hr-thumb", track), thumbHi = elem("hr-thumb", track);
    // Werteanzeige als feste Zeile (links unterer, rechts oberer Wert) statt Blasen an den Griffen:
    // die Blasen ueberlappten sich, sobald die Griffe nah beieinander standen.
    var valsRow = elem("hr-vals", root);
    var bubLo = elem("hr-val", valsRow), bubSep = elem("hr-val-sep", valsRow), bubHi = elem("hr-val", valsRow);
    bubSep.textContent = "–";
    var inLo, inHi;
    if (withInputs) {
      var ir = elem("hr-inputs", root);
      inLo = document.createElement("input"); inHi = document.createElement("input");
      inLo.type = inHi.type = "number"; inLo.step = inHi.step = step;
      inLo.min = inHi.min = dmin; inLo.max = inHi.max = dmax;
      inLo.placeholder = fmt(dmin); inHi.placeholder = fmt(dmax);
      var dash = document.createElement("span"); dash.textContent = "–";
      ir.append(inLo, dash, inHi);
      inLo.addEventListener("change", function () { lo = inLo.value === "" ? dmin : clamp(+inLo.value, dmin, hi); render(); emit(false); });
      inHi.addEventListener("change", function () { hi = inHi.value === "" ? dmax : clamp(+inHi.value, lo, dmax); render(); emit(false); });
    }

    function render() {
      fill.style.left = toPos(lo) * 100 + "%"; fill.style.right = (100 - toPos(hi) * 100) + "%";
      thumbLo.style.left = toPos(lo) * 100 + "%"; thumbHi.style.left = toPos(hi) * 100 + "%";
      bubLo.textContent = fmt(lo); bubHi.textContent = fmt(hi);
      bubLo.classList.toggle("set", lo > dmin); bubHi.classList.toggle("set", hi < dmax);
      if (withInputs) { inLo.value = (lo <= dmin ? "" : lo); inHi.value = (hi >= dmax ? "" : hi); }
      for (var k = 0; k < bars.length; k++) bars[k].classList.toggle("on", centers[k] >= lo && centers[k] <= hi);
    }
    function rangeOut() { return [lo <= dmin ? "" : lo, hi >= dmax ? "" : hi]; }
    function valueAt(clientX) {
      var r = track.getBoundingClientRect();
      var v = toVal((clientX - r.left) / r.width);
      return clamp(Math.round(v / step) * step, dmin, dmax);
    }
    var active = null, tmr = null;
    function emit(live) {
      if (live && opts.onInput) opts.onInput([lo, hi]);
      clearTimeout(tmr);
      tmr = setTimeout(function () { if (opts.onChange) opts.onChange(rangeOut()); }, live ? 110 : 0);
    }
    function move(e) {
      if (!active) return;
      var v = valueAt(e.clientX);
      if (active === "lo") lo = Math.min(v, hi); else hi = Math.max(v, lo);
      render(); emit(true);
    }
    function up() {
      if (!active) return;
      active = null;
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      emit(false);
    }
    function down(which, e) {
      active = which; e.preventDefault();
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    }
    thumbLo.addEventListener("pointerdown", function (e) { down("lo", e); });
    thumbHi.addEventListener("pointerdown", function (e) { down("hi", e); });
    track.addEventListener("pointerdown", function (e) {
      if (e.target === thumbLo || e.target === thumbHi) return;
      var v = valueAt(e.clientX);
      if (Math.abs(v - lo) <= Math.abs(v - hi)) { lo = Math.min(v, hi); down("lo", e); }
      else { hi = Math.max(v, lo); down("hi", e); }
      render(); emit(true);
    });

    render();
    return {
      element: root,
      getRange: rangeOut,
      setRange: function (a, b) {
        lo = (a === "" || a == null) ? dmin : clamp(+a, dmin, dmax);
        hi = (b === "" || b == null) ? dmax : clamp(+b, dmin, dmax);
        render();
      },
      reset: function () { lo = dmin; hi = dmax; render(); }
    };
  }

  global.HistogramRange = HistogramRange;
})(window);
