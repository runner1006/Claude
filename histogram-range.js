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
 *   scale    : "linear" | "quantile"
 *              "quantile" => nicht-lineare Achse: dort wo mehr Werte liegen,
 *              ist die Achse dichter (mehr Platz / feinere Kontrolle).
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
    ".hr{--hr-acc:var(--accent,#b16286);--hr-mut:var(--line,#2a313d);--hr-txt:var(--muted,#9aa4b2);width:100%;user-select:none}" +
    ".hr-top{display:flex;justify-content:space-between;align-items:baseline;font-size:12px;color:var(--hr-txt);margin-bottom:6px}" +
    ".hr-top b{color:var(--text,#e6e9ef);font-weight:600}" +
    ".hr-histo{display:flex;align-items:flex-end;gap:1px;height:42px;margin:0 8px 5px}" +
    ".hr-bar{flex:1 1 0;background:var(--hr-mut);border-radius:2px 2px 0 0;min-height:2px;transition:background .08s}" +
    ".hr-bar.on{background:var(--hr-acc)}" +
    ".hr-track{position:relative;height:22px;margin:0 8px;touch-action:none}" +
    ".hr-rail{position:absolute;left:0;right:0;top:50%;height:5px;transform:translateY(-50%);background:var(--hr-mut);border-radius:3px}" +
    ".hr-fill{position:absolute;top:50%;height:5px;transform:translateY(-50%);background:var(--hr-acc);border-radius:3px}" +
    ".hr-thumb{position:absolute;top:50%;width:16px;height:16px;border-radius:50%;background:#fff;border:2px solid var(--hr-acc);" +
      "transform:translate(-50%,-50%);cursor:grab;box-shadow:0 1px 4px rgba(0,0,0,.45);z-index:2}" +
    ".hr-thumb:active{cursor:grabbing}" +
    ".hr-bubble{position:absolute;top:50%;left:50%;transform:translate(-50%,14px);background:#0b0d11;color:#fff;font-size:11px;" +
      "font-weight:600;padding:1px 7px;border-radius:20px;white-space:nowrap;pointer-events:none;font-variant-numeric:tabular-nums}" +
    ".hr-inputs{display:flex;align-items:center;gap:7px;margin:13px 8px 0}" +
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
    var scale = (opts.scale === "quantile" && n > 1) ? "quantile" : "linear";
    var withInputs = opts.inputs !== false;
    var lo = dmin, hi = dmax;

    // ---- Achsen-Mapping Position<->Wert ----
    function toPos(v) {
      if (scale === "linear") return (v - dmin) / (dmax - dmin);
      if (v <= values[0]) return 0;
      if (v >= values[n - 1]) return 1;
      var a = 0, b = n;
      while (a < b) { var m = (a + b) >> 1; if (values[m] < v) a = m + 1; else b = m; }
      var up = a; while (up < n && values[up] === v) up++;
      return (a + up) / 2 / n;
    }
    function toVal(p) {
      p = clamp(p, 0, 1);
      if (scale === "linear") return dmin + p * (dmax - dmin);
      var idx = p * (n - 1), i = Math.floor(idx), f = idx - i;
      return values[i] + ((values[Math.min(i + 1, n - 1)]) - values[i]) * f;
    }

    // ---- Histogramm-Bins (im Positionsraum; Höhe = Dichte je Wert-Einheit) ----
    var dens = new Array(bins), centers = new Array(bins);
    for (var i = 0; i < bins; i++) {
      var vLo = toVal(i / bins), vHi = toVal((i + 1) / bins);
      if (vHi <= vLo) vHi = vLo + step;
      var c = 0, last = (i === bins - 1);
      for (var j = 0; j < n; j++) { var x = values[j]; if (x >= vLo && (x < vHi || (last && x <= vHi))) c++; }
      dens[i] = c / Math.max(vHi - vLo, step);
      centers[i] = (vLo + vHi) / 2;
    }
    var maxDens = Math.max.apply(null, dens.concat([1e-9]));

    // ---- DOM ----
    var root = elem("hr");
    if (opts.title != null) {
      var top = elem("hr-top", root);
      var ts = document.createElement("span"); ts.textContent = opts.title; top.appendChild(ts);
      if (opts.avg != null) { var as = document.createElement("span"); as.innerHTML = opts.avg; top.appendChild(as); }
    }
    var histo = elem("hr-histo", root);
    var bars = dens.map(function (dv) { var b = elem("hr-bar", histo); b.style.height = (dv / maxDens * 100) + "%"; return b; });
    var track = elem("hr-track", root);
    elem("hr-rail", track);
    var fill = elem("hr-fill", track);
    var thumbLo = elem("hr-thumb", track), thumbHi = elem("hr-thumb", track);
    var bubLo = elem("hr-bubble", thumbLo), bubHi = elem("hr-bubble", thumbHi);
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
