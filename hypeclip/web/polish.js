/* HypeClip Design System - Apple-grade polish layer.
   Tokens, motion, switches, appearance studio, optional UI sounds. */
(function () {
  if (window.__hcPolishLoaded) return;
  window.__hcPolishLoaded = true;

  var DEF = {
    preset: "dark", accent: "#7c5cff", accent2: "#38e08e",
    radius: 16, motion: 1, blur: 16, font: 14, density: 1,
    reduced: false, contrast: false, sounds: false
  };
  var S = Object.assign({}, DEF);
  try { Object.assign(S, JSON.parse(localStorage.getItem("hcTheme") || "{}")); }
  catch (e) {}
  var saved = {};
  try { saved = JSON.parse(localStorage.getItem("hcThemes") || "{}"); }
  catch (e) {}

  function persist() {
    try { localStorage.setItem("hcTheme", JSON.stringify(S)); } catch (e) {}
  }

  var PRESETS = {
    dark:    { bg: "#0b0e1a", surface: "rgba(21,26,44,.86)", text: "#e8ecff",
               sub: "#9aa3c7", border: "rgba(255,255,255,.09)", glass: 1 },
    oled:    { bg: "#000000", surface: "rgba(10,10,12,.92)", text: "#f2f4ff",
               sub: "#8b93b8", border: "rgba(255,255,255,.08)", glass: 0 },
    midnight:{ bg: "#070b18", surface: "rgba(14,20,40,.9)",  text: "#dfe6ff",
               sub: "#8d97c2", border: "rgba(120,140,255,.12)", glass: 1 },
    frosted: { bg: "rgba(18,22,38,.55)", surface: "rgba(30,36,60,.5)",
               text: "#f0f3ff", sub: "#aeb6d8",
               border: "rgba(255,255,255,.14)", glass: 1 },
    light:   { bg: "#f4f6fb", surface: "rgba(255,255,255,.88)", text: "#171b2e",
               sub: "#5c6480", border: "rgba(20,30,60,.1)", glass: 1 }
  };

  var css = [
    ":root{--ac:", ";--ac2:", ";--r:", "px;--ms:", ";--bl:", "px;",
    "--fs:", "px;--dn:", ";--bg:", ";--surf:", ";--txt:", ";--sub:", ";",
    "--bd:", ";--dur:calc(180ms*var(--ms));--ease:cubic-bezier(.22,1,.36,1);",
    "--spring:cubic-bezier(.34,1.56,.64,1)}"
  ].join("");
  var head = document.head;
  var base = document.createElement("style");
  head.appendChild(base);

  function hexA(h, a) {
    h = h.replace("#", "");
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16);
    return "rgba(" + ((n >> 16) & 255) + "," + ((n >> 8) & 255) + "," +
      (n & 255) + "," + a + ")";
  }

  var sheet = document.createElement("style");
  function buildCSS() {
    var p = PRESETS[S.preset] || PRESETS.dark;
    var t = [":root{--ac:" + S.accent + ";--ac2:" + S.accent2 +
      ";--r:" + S.radius + "px;--ms:" + S.motion + ";--bl:" + S.blur +
      "px;--fs:" + S.font + "px;--dn:" + S.density + ";--bg:" + p.bg +
      ";--surf:" + p.surface + ";--txt:" + p.text + ";--sub:" + p.sub +
      ";--bd:" + p.border + ";--glass:" + p.glass + "}"];
    t.push('html{font-size:var(--fs)}body,html{scroll-behavior:smooth}');
    t.push("body{background:var(--bg) !important;color:var(--txt) !important;" +
      "font-family:-apple-system,'SF Pro Text','Segoe UI Variable'," +
      "'Segoe UI',Roboto,Inter,sans-serif !important;" +
      "letter-spacing:.01em;-webkit-font-smoothing:antialiased}");
    t.push("*{scrollbar-width:thin;scrollbar-color:" + hexA(S.accent, .5) +
      " transparent}");
    t.push("::-webkit-scrollbar{width:8px;height:8px}::-webkit-scrollbar-thumb{" +
      "background:" + hexA(S.accent, .45) + ";border-radius:99px}" +
      "::-webkit-scrollbar-track{background:transparent}");
    /* buttons: universal premium treatment */
    t.push("button,.btn{border-radius:calc(var(--r) * .62) !important;" +
      "transition:transform var(--dur) var(--spring)," +
      "box-shadow var(--dur) var(--ease),background var(--dur) var(--ease)," +
      "filter var(--dur) var(--ease),border-color var(--dur) var(--ease) " +
      "!important;will-change:transform}");
    t.push("button:hover:not(:disabled){transform:translateY(-1px) " +
      "scale(1.02);filter:brightness(1.12)}");
    t.push("button:active:not(:disabled){transform:scale(.965);" +
      "transition-duration:calc(60ms * var(--ms))}");
    t.push("button:focus-visible,input:focus-visible,select:focus-visible," +
      "video:focus-visible{outline:2px solid " + hexA(S.accent, .8) +
      ";outline-offset:2px;border-radius:calc(var(--r) * .5)}");
    t.push("button:disabled{opacity:.45;filter:saturate(.4)}");
    /* inputs */
    t.push("input[type=text],input[type=url],input[type=number],input," +
      "select,textarea{border-radius:calc(var(--r) * .55) !important;" +
      "transition:border-color var(--dur) var(--ease)," +
      "box-shadow var(--dur) var(--ease) !important}");
    t.push("input:focus,select:focus,textarea:focus{border-color:" +
      hexA(S.accent, .7) + " !important;box-shadow:0 0 0 3px " +
      hexA(S.accent, .22) + " !important;outline:none}");
    t.push("input[type=range]{accent-color:var(--ac);height:4px}");
    /* modern switches for every checkbox */
    t.push('input[type=checkbox]{appearance:none;-webkit-appearance:none;' +
      "width:40px;height:24px;border-radius:99px;background:rgba(128,138,168," +
      ".35);position:relative;cursor:pointer;flex:none;" +
      "transition:background var(--dur) var(--ease)," +
      "transform var(--dur) var(--spring) !important;margin:0}");
    t.push('input[type=checkbox]::after{content:"";position:absolute;top:3px;' +
      "left:3px;width:18px;height:18px;border-radius:50%;background:#fff;" +
      "box-shadow:0 2px 6px rgba(0,0,0,.35);" +
      "transition:left var(--dur) var(--spring),width var(--dur) var(--ease)}");
    t.push("input[type=checkbox]:hover{transform:scale(1.06)}" +
      "input[type=checkbox]:active{transform:scale(.94)}" +
      "input[type=checkbox]:checked{background:linear-gradient(90deg," +
      "var(--ac),var(--ac2))}input[type=checkbox]:checked::after{left:19px}");
    /* popovers + modals: cinematic entrance */
    t.push("@keyframes hcIn{from{opacity:0;transform:translateY(14px) " +
      "scale(.955);filter:blur(6px)}to{opacity:1;transform:none;filter:none}}");
    t.push("@keyframes hcOut{to{opacity:0;transform:translateY(8px) " +
      "scale(.97);filter:blur(4px)}}");
    var sel = ".hrv-mod.open .hrv-mw,.hrv.open .hrv-h,.hrv.open .hrv-body," +
      ".hrv-face.open>*,.hcrt,.hcvre,.hrvbtn,.hggbtn";
    t.push(sel + "{animation:hcIn calc(340ms*var(--ms)) var(--ease) both}");
    t.push(".hrv-mod,.hrv,.hrv-face{transition:background var(--dur) " +
      "var(--ease),backdrop-filter var(--dur) var(--ease)}");
    /* cards lift */
    t.push(".hrv-card,.hrv-row,.hrv-col,.hcrt-row,.hcvre-bp,.hrv-mw,.hrv-fx{" +
      "border-radius:var(--r) !important;transition:transform var(--dur) " +
      "var(--ease),box-shadow var(--dur) var(--ease)," +
      "border-color var(--dur) var(--ease) !important}");
    t.push(".hrv-card:hover,.hrv-col:hover,.hcrt-row:hover," +
      ".hcvre-bp:hover{box-shadow:0 16px 44px rgba(0,0,0,.5),0 0 0 1.5px " +
      hexA(S.accent, .55) + " !important}");
    /* panel surfaces unify with theme */
    t.push(".hcrt,.hcvre,.hrv-fx,.hrv-toast{background:var(--surf) !important;" +
      "border:1px solid var(--bd) !important;backdrop-filter:" +
      "blur(calc(var(--bl) * var(--glass))) saturate(1.3) !important;" +
      "color:var(--txt) !important}");
    t.push(".hrv{background:rgba(6,8,16," +
      (S.preset === "frosted" ? ".45" : ".72") +
      ") !important;backdrop-filter:blur(calc(var(--bl) + 6px)) !important}");
    t.push(".hrv-empty,.hcvre-empty,.hcrt-empty,.hrv-c,.hcvre-lab," +
      ".hcrt-verdict,.hrv-fx-note{color:var(--sub) !important}");
    t.push(".hrv-chip,.hcvre-chip,.hcrt-badge{border-radius:99px !important}");
    /* skeletons for media placeholders */
    t.push("@keyframes hcSh{0%{background-position:-300px 0}100%{" +
      "background-position:300px 0}}");
    t.push(".hrv-ph,.hgg-ph{background:linear-gradient(100deg,#151a2c 40%," +
      hexA(S.accent, .1) + " 50%,#151a2c 60%) !important;" +
      "background-size:600px 100% !important;animation:hcSh 1.6s " +
      "linear infinite !important;border-radius:calc(var(--r)*.8)}");
    /* high contrast + reduced motion */
    t.push("html.hc-contrast *{text-shadow:none !important}" +
      "html.hc-contrast{--bd:rgba(255,255,255,.4)}" +
      "html.hc-contrast .hrv-chip,html.hc-contrast .hrv-b{border:1px solid " +
      "rgba(255,255,255,.5)}");
    t.push("html.hc-reduced *{animation-duration:1ms !important;" +
      "transition-duration:1ms !important;scroll-behavior:auto !important}");
    t.push("@media (prefers-reduced-motion:reduce){html:not(.hc-force-m) *" +
      "{animation-duration:1ms !important;transition-duration:1ms !important}}");
    base.textContent = t.join("\n");
  }
  function apply() {
    buildCSS();
    document.documentElement.classList.toggle("hc-reduced", !!S.reduced);
    document.documentElement.classList.toggle("hc-contrast", !!S.contrast);
    if (S.reduced) document.documentElement.classList.add("hc-force-m");
    else document.documentElement.classList.remove("hc-force-m");
    persist();
  }

  /* ---------------- optional UI sounds (WebAudio, off by default) ------ */
  var AC = null;
  function tone(freq, dur, type, gain) {
    try {
      AC = AC || new (window.AudioContext || window.webkitAudioContext)();
      var o = AC.createOscillator(), g = AC.createGain();
      o.type = type || "sine"; o.frequency.value = freq;
      g.gain.setValueAtTime(gain || .06, AC.currentTime);
      g.gain.exponentialRampToValueAtTime(.0001, AC.currentTime + dur);
      o.connect(g).connect(AC.destination);
      o.start(); o.stop(AC.currentTime + dur);
    } catch (e) {}
  }
  function clickSnd() { tone(1900, .045, "sine", .035); }
  function chime() {
    tone(880, .12, "sine", .05);
    setTimeout(function () { tone(1318.5, .2, "sine", .05); }, 90);
  }
  document.addEventListener("click", function (e) {
    if (S.sounds && e.target.closest && e.target.closest("button")) clickSnd();
  }, true);

  /* ---------------- appearance studio ---------------- */
  var fab = document.createElement("button");
  fab.innerHTML = "🎨";
  fab.title = "Appearance";
  fab.style.cssText = "position:fixed;top:14px;right:14px;z-index:100000;" +
    "width:40px;height:40px;border:none;border-radius:13px;cursor:pointer;" +
    "color:#fff;font-size:17px;background:linear-gradient(135deg," +
    "rgba(124,92,255,.9),rgba(56,224,142,.85));box-shadow:0 8px 24px " +
    "rgba(0,0,0,.4)";
  document.body.appendChild(fab);

  var st = document.createElement("div");
  st.style.cssText = "position:fixed;top:62px;right:14px;z-index:100001;" +
    "width:284px;max-height:80vh;overflow-y:auto;display:none;color:var(--txt);" +
    "background:var(--surf);border:1px solid var(--bd);border-radius:18px;" +
    "padding:14px;backdrop-filter:blur(20px) saturate(1.4);" +
    "box-shadow:0 20px 60px rgba(0,0,0,.5);font:13px/1.5 -apple-system," +
    "'Segoe UI',Roboto,sans-serif";
  document.body.appendChild(st);
  fab.onclick = function () {
    st.style.display = st.style.display === "block" ? "none" : "block";
  };
  document.addEventListener("click", function (e) {
    if (st.style.display === "block" && !st.contains(e.target) &&
        e.target !== fab) st.style.display = "none";
  });

  function row(label, ctrl) {
    var d = document.createElement("div");
    d.style.cssText = "display:flex;align-items:center;gap:10px;margin:9px 0";
    var l = document.createElement("span");
    l.textContent = label;
    l.style.cssText = "flex:1;font-size:12.5px";
    d.appendChild(l); d.appendChild(ctrl);
    return d;
  }
  function slider(min, max, step, val, fn) {
    var i = document.createElement("input");
    i.type = "range"; i.min = min; i.max = max; i.step = step;
    i.value = val; i.style.width = "130px";
    i.oninput = function () { fn(parseFloat(i.value)); };
    return i;
  }
  function renderStudio() {
    st.innerHTML = "";
    var h = document.createElement("div");
    h.textContent = "APPEARANCE";
    h.style.cssText = "font-weight:800;letter-spacing:.1em;font-size:11px;" +
      "color:var(--sub);margin-bottom:4px";
    st.appendChild(h);
    var presets = document.createElement("div");
    presets.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin:8px 0";
    Object.keys(PRESETS).forEach(function (k) {
      var b = document.createElement("button");
      b.textContent = k;
      b.style.cssText = "padding:6px 11px;font-size:11px;font-weight:700;" +
        "cursor:pointer;border:1px solid " + (S.preset === k
          ? hexA(S.accent, .8) : "var(--bd)") + ";border-radius:9px;" +
        "background:" + (S.preset === k ? hexA(S.accent, .25) : "transparent") +
        ";color:var(--txt)";
      b.onclick = function () { S.preset = k; apply(); renderStudio(); };
      presets.appendChild(b);
    });
    st.appendChild(presets);
    var ac = document.createElement("input");
    ac.type = "color"; ac.value = S.accent; ac.style.cssText =
      "width:44px;height:28px;border:none;background:none;cursor:pointer";
    ac.oninput = function () { S.accent = ac.value; apply(); };
    st.appendChild(row("Accent", ac));
    var ac2 = document.createElement("input");
    ac2.type = "color"; ac2.value = S.accent2; ac2.style.cssText =
      "width:44px;height:28px;border:none;background:none;cursor:pointer";
    ac2.oninput = function () { S.accent2 = ac2.value; apply(); };
    st.appendChild(row("Secondary accent", ac2));
    st.appendChild(row("Corner radius",
      slider(0, 26, 1, S.radius, function (v) { S.radius = v; apply(); })));
    st.appendChild(row("Animation speed",
      slider(0.4, 2, 0.05, S.motion, function (v) { S.motion = v; apply(); })));
    st.appendChild(row("Blur strength",
      slider(0, 34, 1, S.blur, function (v) { S.blur = v; apply(); })));
    st.appendChild(row("Font size",
      slider(12, 18, 0.5, S.font, function (v) { S.font = v; apply(); })));
    st.appendChild(row("UI density",
      slider(0.85, 1.3, 0.05, S.density, function (v) { S.density = v; apply(); })));
    function tgl(label, key) {
      var i = document.createElement("input");
      i.type = "checkbox"; i.checked = !!S[key];
      i.onchange = function () { S[key] = i.checked; apply(); renderStudio(); };
      return row(label, i);
    }
    st.appendChild(tgl("Reduced motion", "reduced"));
    st.appendChild(tgl("High contrast", "contrast"));
    st.appendChild(tgl("UI sounds", "sounds"));
    /* saved themes */
    var sh = document.createElement("div");
    sh.textContent = "SAVED THEMES";
    sh.style.cssText = "font-weight:800;letter-spacing:.1em;font-size:10px;" +
      "color:var(--sub);margin:12px 0 4px";
    st.appendChild(sh);
    var names = Object.keys(saved);
    if (!names.length) {
      var none = document.createElement("div");
      none.textContent = "No saved themes yet";
      none.style.cssText = "font-size:11px;color:var(--sub);margin:4px 0";
      st.appendChild(none);
    }
    names.forEach(function (n) {
      var d = document.createElement("div");
      d.style.cssText = "display:flex;gap:6px;align-items:center;margin:5px 0";
      var b = document.createElement("button");
      b.textContent = n;
      b.style.cssText = "flex:1;padding:7px;font-size:11.5px;font-weight:700;" +
        "cursor:pointer;border:1px solid var(--bd);border-radius:9px;" +
        "background:transparent;color:var(--txt)";
      b.onclick = function () {
        S = Object.assign({}, DEF, saved[n]); apply(); renderStudio();
      };
      var del = document.createElement("button");
      del.textContent = "✕";
      del.style.cssText = "width:26px;height:26px;border:none;border-radius:8px;" +
        "cursor:pointer;background:rgba(255,93,93,.2);color:#ff8d8d";
      del.onclick = function () {
        delete saved[n];
        try { localStorage.setItem("hcThemes", JSON.stringify(saved)); }
        catch (e) {}
        renderStudio();
      };
      d.appendChild(b); d.appendChild(del);
      st.appendChild(d);
    });
    var sv = document.createElement("button");
    sv.textContent = "＋ Save current as theme";
    sv.style.cssText = "width:100%;margin-top:8px;padding:9px;font-weight:800;" +
      "font-size:11.5px;cursor:pointer;border:none;border-radius:10px;" +
      "color:#fff;background:linear-gradient(90deg,var(--ac),var(--ac2))";
    sv.onclick = function () {
      var n = prompt("Theme name:", "My theme " +
        (Object.keys(saved).length + 1));
      if (!n) return;
      saved[n] = Object.assign({}, S);
      try { localStorage.setItem("hcThemes", JSON.stringify(saved)); }
      catch (e) {}
      renderStudio();
    };
    st.appendChild(sv);
    var rst = document.createElement("button");
    rst.textContent = "Reset to defaults";
    rst.style.cssText = "width:100%;margin-top:6px;padding:8px;font-size:11px;" +
      "cursor:pointer;border:1px solid var(--bd);border-radius:10px;" +
      "background:transparent;color:var(--sub)";
    rst.onclick = function () { S = Object.assign({}, DEF); apply(); renderStudio(); };
    st.appendChild(rst);
  }

  /* ---------------- completion chime on job finish ---------------- */
  var of = window.fetch;
  window.fetch = function () {
    var url = "";
    try {
      var a0 = arguments[0];
      url = typeof a0 === "string" ? a0 : (a0 && a0.url) || "";
    } catch (e) {}
    var p = of.apply(this, arguments);
    if (url.indexOf("/api/jobs/") > -1) {
      p.then(function (r) {
        try {
          r.clone().json().then(function (d) {
            if (d && d.state === "done" && d.clips && d.clips.length &&
                !d.__hcChimed) {
              if (S.sounds) chime();
            }
          }).catch(function () {});
        } catch (e) {}
      }).catch(function () {});
    }
    return p;
  };

  apply();
  renderStudio();
})();
