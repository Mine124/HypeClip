/* HypeClip Design System v2 - motion engine, FLIP shared elements,
   staggered entrances, extended theme engine, tooltips, toasts. */
(function () {
  if (window.__hcPolishLoaded) return;
  window.__hcPolishLoaded = true;
  console.log("[polish] v2 ACTIVE");

  var DEF = {
    preset: "dark", accent: "#7c5cff", accent2: "#38e08e",
    radius: 16, motion: 1, blur: 16, font: 14, density: 1,
    shadow: 1, alpha: 0.88,
    bgColor: "", surfColor: "", txtColor: "",
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

  function hexA(h, a) {
    h = String(h).replace("#", "");
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16);
    if (isNaN(n)) return "rgba(21,26,44," + a + ")";
    return "rgba(" + ((n >> 16) & 255) + "," + ((n >> 8) & 255) + "," +
      (n & 255) + "," + a + ")";
  }
  function mulAlpha(rgba, m) {
    var mm = rgba.match(/rgba?\(([^)]+)\)/);
    if (!mm) return rgba;
    var p = mm[1].split(",").map(function (x) { return x.trim(); });
    var a = 1;
    if (p.length > 3) a = parseFloat(p[3]);
    a = Math.max(0, Math.min(1, a * m));
    return "rgba(" + p[0] + "," + p[1] + "," + p[2] + "," +
      a.toFixed(3) + ")";
  }
  function reduced() {
    return S.reduced || (window.matchMedia &&
      matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  /* ------------------------------------------------------------ tokens */
  var base = document.createElement("style");
  document.head.appendChild(base);
  function buildCSS() {
    var p = PRESETS[S.preset] || PRESETS.dark;
    var bg = S.bgColor || p.bg;
    var surf = S.surfColor
      ? hexA(S.surfColor, Math.max(0.3, Math.min(1, S.alpha)))
      : (S.alpha !== DEF.alpha ? mulAlpha(p.surface, S.alpha / DEF.alpha)
                               : p.surface);
    var txt = S.txtColor || p.text;
    var t = [":root{--ac:" + S.accent + ";--ac2:" + S.accent2 +
      ";--r:" + S.radius + "px;--ms:" + S.motion + ";--bl:" + S.blur +
      "px;--fs:" + S.font + "px;--dn:" + S.density + ";--sh:" + S.shadow +
      ";--bg:" + bg + ";--surf:" + surf + ";--txt:" + txt +
      ";--sub:" + p.sub + ";--bd:" + p.border + ";--glass:" + p.glass +
      /* motion hierarchy: heavy / mid / light / micro */
      ";--dur-h:calc(380ms*var(--ms));--dur-m:calc(240ms*var(--ms));" +
      "--dur-l:calc(150ms*var(--ms));--dur-x:calc(80ms*var(--ms));" +
      "--ease:cubic-bezier(.22,1,.36,1);" +
      "--spring:cubic-bezier(.34,1.56,.64,1)}"];
    t.push('html{font-size:var(--fs)}body,html{scroll-behavior:smooth}');
    t.push("body{background:var(--bg) !important;color:var(--txt) !important;" +
      "font-family:-apple-system,'SF Pro Text','Segoe UI Variable'," +
      "'Segoe UI',Roboto,Inter,sans-serif !important;letter-spacing:.01em;" +
      "-webkit-font-smoothing:antialiased}");
    t.push("*{scrollbar-width:thin;scrollbar-color:" + hexA(S.accent, .5) +
      " transparent}::-webkit-scrollbar{width:8px;height:8px}" +
      "::-webkit-scrollbar-thumb{background:" + hexA(S.accent, .45) +
      ";border-radius:99px}::-webkit-scrollbar-track{background:transparent}");
    t.push(".hrv-body,.hcvre-b,.hcrt-b,.hrv-fx{overscroll-behavior:contain}");
    /* buttons */
    t.push("button,.btn{border-radius:calc(var(--r) * .62) !important;" +
      "transition:transform var(--dur-m) var(--spring)," +
      "box-shadow var(--dur-m) var(--ease),background var(--dur-m) var(--ease)," +
      "filter var(--dur-m) var(--ease) !important;will-change:transform}");
    t.push("button:hover:not(:disabled){transform:translateY(-1px) " +
      "scale(1.02);filter:brightness(1.12)}");
    t.push("button:active:not(:disabled){transform:scale(.965);" +
      "transition-duration:var(--dur-x)}");
    t.push("button:focus-visible,input:focus-visible,select:focus-visible{" +
      "outline:2px solid " + hexA(S.accent, .8) + ";outline-offset:2px}");
    t.push("button:disabled{opacity:.45;filter:saturate(.4)}");
    /* inputs */
    t.push("input,select,textarea{border-radius:calc(var(--r) * .55)" +
      " !important;transition:border-color var(--dur-m) var(--ease)," +
      "box-shadow var(--dur-m) var(--ease) !important}");
    t.push("input:focus,select:focus,textarea:focus{border-color:" +
      hexA(S.accent, .7) + " !important;box-shadow:0 0 0 3px " +
      hexA(S.accent, .22) + " !important;outline:none}");
    t.push("input[type=range]{accent-color:var(--ac);height:4px}");
    /* switches */
    t.push('input[type=checkbox]{appearance:none;-webkit-appearance:none;' +
      "width:40px;height:24px;border-radius:99px;background:rgba(128,138,168," +
      ".35);position:relative;cursor:pointer;flex:none;margin:0;" +
      "transition:background var(--dur-m) var(--ease)," +
      "transform var(--dur-m) var(--spring) !important}");
    t.push('input[type=checkbox]::after{content:"";position:absolute;top:3px;' +
      "left:3px;width:18px;height:18px;border-radius:50%;background:#fff;" +
      "box-shadow:0 2px 6px rgba(0,0,0,.35);transition:left var(--dur-m)" +
      " var(--spring)}");
    t.push("input[type=checkbox]:hover{transform:scale(1.06)}" +
      "input[type=checkbox]:active{transform:scale(.94)}" +
      "input[type=checkbox]:checked{background:linear-gradient(90deg," +
      "var(--ac),var(--ac2))}input[type=checkbox]:checked::after{left:19px}");
    /* keyframes */
    t.push("@keyframes hcIn{from{opacity:0;transform:translateY(14px) " +
      "scale(.955);filter:blur(6px)}to{opacity:1;transform:none;filter:none}}");
    t.push("@keyframes hcSh{0%{background-position:-300px 0}100%{" +
      "background-position:300px 0}}");
    t.push(".hrv-mod.open .hrv-mw,.hrv.open .hrv-h,.hrv.open .hrv-body," +
      ".hrv-face.open>*,.hcrt,.hcvre,.hrvbtn{animation:hcIn var(--dur-h)" +
      " var(--ease) both}");
    /* cards + surfaces */
    t.push(".hrv-card,.hrv-row,.hrv-col,.hcrt-row,.hcvre-bp,.hrv-mw,.hrv-fx{" +
      "border-radius:var(--r) !important;transition:transform var(--dur-m)" +
      " var(--ease),box-shadow var(--dur-m) var(--ease)," +
      "border-color var(--dur-m) var(--ease) !important}");
    t.push(".hrv-card:hover,.hrv-col:hover,.hcrt-row:hover,.hcvre-bp:hover{" +
      "box-shadow:0 calc(16px*var(--sh)) calc(44px*var(--sh)) rgba(0,0,0," +
      (0.5 * Math.min(1.4, S.shadow)).toFixed(2) + "),0 0 0 1.5px " +
      hexA(S.accent, .55) + " !important}");
    t.push(".hcrt,.hcvre,.hrv-fx,.hrv-toast,.hrv-sel,.hrv-ver,.hrv-seg{" +
      "background:var(--surf) !important;border:1px solid var(--bd)" +
      " !important;backdrop-filter:blur(calc(var(--bl) * var(--glass)))" +
      " saturate(1.3) !important;color:var(--txt) !important}");
    t.push(".hrv{background:rgba(6,8,16," +
      (S.preset === "frosted" ? ".45" : ".72") + ") !important;" +
      "backdrop-filter:blur(calc(var(--bl) + 6px)) !important}");
    t.push(".hrv-empty,.hcvre-empty,.hcrt-empty,.hrv-c,.hcvre-lab," +
      ".hcrt-verdict,.hrv-fx-note,.hrv-sub{color:var(--sub) !important}");
    t.push(".hrv-chip,.hcvre-chip,.hcrt-badge{border-radius:99px !important}");
    /* skeleton shimmer */
    t.push(".hrv-ph,.hgg-ph,.hrv-mth:not([src])" +
      "{background:linear-gradient(100deg,#151a2c 40%," +
      hexA(S.accent, .1) + " 50%,#151a2c 60%) !important;" +
      "background-size:600px 100% !important;animation:hcSh 1.6s linear" +
      " infinite !important;border-radius:calc(var(--r)*.8)}");
    /* accessibility */
    t.push("html.hc-contrast *{text-shadow:none !important}" +
      "html.hc-contrast{--bd:rgba(255,255,255,.4)}" +
      "html.hc-contrast .hrv-chip,html.hc-contrast .hrv-b{border:1px solid " +
      "rgba(255,255,255,.5)}");
    t.push("html.hc-reduced *{animation-duration:1ms !important;" +
      "transition-duration:1ms !important;scroll-behavior:auto !important}");
    t.push("@media (prefers-reduced-motion:reduce){html:not(.hc-force-m) *{" +
      "animation-duration:1ms !important;transition-duration:1ms !important}}");
    /* smooth theme switch */
    t.push("html.hc-theming *,html.hc-theming *::before," +
      "html.hc-theming *::after{transition:background-color .35s var(--ease)," +
      "color .35s var(--ease),border-color .35s var(--ease) !important}");
    /* tooltips + toasts */
    t.push(".hc-tip{position:fixed;z-index:100003;pointer-events:none;" +
      "background:rgba(10,12,24,.94);color:#eef1ff;border:1px solid " +
      "var(--bd);border-radius:9px;padding:6px 10px;font:600 11.5px/1.4 " +
      "-apple-system,'Segoe UI',Roboto,sans-serif;max-width:260px;" +
      "box-shadow:0 10px 30px rgba(0,0,0,.5)}");
    t.push(".hc-toast{position:fixed;top:16px;left:50%;transform:" +
      "translateX(-50%);z-index:100004;display:flex;gap:9px;align-items:" +
      "center;background:var(--surf);border:1px solid var(--bd);color:" +
      "var(--txt);padding:11px 16px;border-radius:13px;font:600 12.5px/1.4" +
      " -apple-system,'Segoe UI',Roboto,sans-serif;max-width:78vw;" +
      "backdrop-filter:blur(18px);box-shadow:0 14px 44px rgba(0,0,0,.5)}");
    t.push(".hc-toast.ok{border-color:rgba(56,224,142,.5)}" +
      ".hc-toast.err{border-color:rgba(255,93,93,.5)}" +
      ".hc-toast.warn{border-color:rgba(255,209,102,.5)}");
    t.push(".hc-flip{position:fixed;z-index:100003;object-fit:cover;" +
      "pointer-events:none;border-radius:16px;transform-origin:top left;" +
      "box-shadow:0 24px 80px rgba(0,0,0,.6)}");
    base.textContent = t.join("\n");
  }
  function apply(theming) {
    if (theming && !reduced()) {
      document.documentElement.classList.add("hc-theming");
      clearTimeout(apply._tm);
      apply._tm = setTimeout(function () {
        document.documentElement.classList.remove("hc-theming");
      }, 420);
    }
    buildCSS();
    document.documentElement.classList.toggle("hc-reduced", !!S.reduced);
    document.documentElement.classList.toggle("hc-contrast", !!S.contrast);
    if (S.reduced) document.documentElement.classList.add("hc-force-m");
    else document.documentElement.classList.remove("hc-force-m");
    persist();
  }

  /* ---------------------------------------------------- motion engine */
  var EASE = "cubic-bezier(.22,1,.36,1)";
  var SPRING = "cubic-bezier(.34,1.56,.64,1)";
  function animate(el, kf, opts) {
    if (!el || reduced()) return null;
    try {
      if (el._hcAnim) { try { el._hcAnim.cancel(); } catch (e) {} }
      var a = el.animate(kf, Object.assign({ easing: EASE,
        fill: "both" }, opts || {}));
      el._hcAnim = a;
      return a;
    } catch (e) { return null; }
  }
  function stagger(nodes, fn, gap) {
    if (reduced()) return;
    gap = gap || 28;
    var list = Array.prototype.slice.call(nodes).slice(0, 12);
    list.forEach(function (el, i) {
      if (el._hcStag) return;
      el._hcStag = true;
      animate(el, [{ opacity: 0, transform: "translateY(12px)" },
                   { opacity: 1, transform: "none" }],
        { duration: 300, delay: i * gap, fill: "backwards" });
      if (fn) fn(el, i);
    });
  }
  window.HC = {
    motion: { animate: animate, stagger: stagger, ease: EASE,
              spring: SPRING, reduced: reduced },
    theme: S
  };

  /* ------------------------------------------- staggered entrances */
  var bodyObs = new MutationObserver(function (muts) {
    if (reduced()) return;
    muts.forEach(function (m) {
      var added = Array.prototype.filter.call(m.addedNodes || [],
        function (n) { return n.nodeType === 1; });
      var targets = added.filter(function (n) {
        return n.classList && (n.classList.contains("hrv-row") ||
               n.classList.contains("hrv-card"));
      });
      if (targets.length) stagger(targets);
    });
  });
  function watchBody() {
    var b = document.querySelector(".hrv-body");
    if (b) { bodyObs.observe(b, { childList: true }); return true; }
    return false;
  }
  var wTries = 0;
  var wTm = setInterval(function () {
    if (watchBody() || ++wTries > 60) clearInterval(wTm);
  }, 1000);

  /* -------------------------------- FLIP shared-element transitions */
  var FLIP = { el: null, rect: null, src: "" };
  document.addEventListener("click", function (e) {
    if (reduced()) return;
    if (e.target.closest && e.target.closest("a,button,label,input")) return;
    var card = e.target.closest ?
      e.target.closest(".hrv-card,.hrv-col,.hrv-mth") : null;
    if (!card) return;
    var img = card.tagName === "IMG" ? card : card.querySelector("img");
    FLIP.el = card;
    FLIP.rect = card.getBoundingClientRect();
    FLIP.src = img ? (img.currentSrc || img.src) : "";
    var frames = 0;
    (function tryIn() {
      var mod = document.querySelector(".hrv-mod.open");
      var mv = mod ? mod.querySelector(".hrv-mv") : null;
      if (mod && mv && FLIP.src) { flipIn(mv); return; }
      if (++frames < 24) requestAnimationFrame(tryIn);
    })();
  }, true);

  function flipIn(mv) {
    var from = FLIP.rect;
    var to = mv.getBoundingClientRect();
    if (!from || !to.width) return;
    var c = document.createElement("img");
    c.className = "hc-flip";
    c.src = FLIP.src;
    c.style.left = from.left + "px";
    c.style.top = from.top + "px";
    c.style.width = from.width + "px";
    c.style.height = from.height + "px";
    document.body.appendChild(c);
    var dx = to.left - from.left, dy = to.top - from.top;
    var sx = to.width / from.width, sy = to.height / from.height;
    var a = animate(c,
      [{ transform: "translate(0,0) scale(1,1)", opacity: 1 },
       { transform: "translate(" + dx + "px," + dy + "px) scale(" +
         sx + "," + sy + ")", opacity: .92 }],
      { duration: 360 });
    try {
      mv.animate([{ opacity: 0 }, { opacity: 1 }],
        { duration: 220, delay: 170, fill: "backwards", easing: EASE });
    } catch (e) {}
    var done = function () {
      setTimeout(function () {
        animate(c, [{ opacity: .92 }, { opacity: 0 }],
          { duration: 130 }).onfinish = function () { c.remove(); };
      }, 40);
    };
    if (a) a.onfinish = done; else c.remove();
  }

  /* ------------------------------------------------------ tooltips */
  var tip = null;
  document.addEventListener("mouseover", function (e) {
    var t = e.target.closest ? e.target.closest("[data-tip]") : null;
    if (!t) return;
    if (!tip) {
      tip = document.createElement("div");
      tip.className = "hc-tip";
      document.body.appendChild(tip);
    }
    tip.textContent = t.getAttribute("data-tip");
    tip.style.display = "block";
    var r = t.getBoundingClientRect();
    var x = Math.max(8, Math.min(window.innerWidth - 270,
      r.left + r.width / 2 - 120));
    tip.style.left = x + "px";
    tip.style.top = (r.bottom + 8 > window.innerHeight - 50
      ? r.top - 40 : r.bottom + 8) + "px";
    animate(tip, [{ opacity: 0, transform: "translateY(-4px)" },
                  { opacity: 1, transform: "none" }],
      { duration: 130 });
  });
  document.addEventListener("mouseout", function (e) {
    if (tip && e.target.closest &&
        e.target.closest("[data-tip]")) tip.style.display = "none";
  });

  /* ----------------------------------------------- sounds + toasts */
  var AC = null;
  function tone(f, d, g, type) {
    try {
      AC = AC || new (window.AudioContext || window.webkitAudioContext)();
      var o = AC.createOscillator(), gn = AC.createGain();
      o.type = type || "sine"; o.frequency.value = f;
      gn.gain.setValueAtTime(g || .05, AC.currentTime);
      gn.gain.exponentialRampToValueAtTime(.0001, AC.currentTime + d);
      o.connect(gn).connect(AC.destination);
      o.start(); o.stop(AC.currentTime + d);
    } catch (e) {}
  }
  document.addEventListener("click", function (e) {
    if (S.sounds && e.target.closest && e.target.closest("button"))
      tone(1900, .045, .03);
  }, true);
  var TOAST_ICON = { ok: "\u2713", err: "\u2717", warn: "!",
                     info: "\u2139" };
  function toast(msg, type, ms) {
    type = TOAST_ICON[type] ? type : "info";
    var t = document.createElement("div");
    t.className = "hc-toast " + type;
    t.innerHTML = '<span style="font-weight:800;color:' +
      (type === "ok" ? "#38e08e" : type === "err" ? "#ff5d5d" :
       type === "warn" ? "#ffd166" : "var(--ac)") + '">' +
      TOAST_ICON[type] + "</span><span>" + msg + "</span>";
    document.body.appendChild(t);
    animate(t, [{ opacity: 0, transform: "translate(-50%,-10px) scale(.96)" },
                { opacity: 1, transform: "translateX(-50%) scale(1)" }],
      { duration: 260 });
    if (S.sounds) {
      if (type === "ok") { tone(880, .12); setTimeout(function () {
        tone(1318.5, .18); }, 90); }
      else if (type === "err") tone(220, .2, .05, "triangle");
    }
    setTimeout(function () {
      var a = animate(t, [{ opacity: 1 }, { opacity: 0,
        transform: "translate(-50%,-8px)" }], { duration: 220 });
      if (a) a.onfinish = function () { t.remove(); };
      else t.remove();
    }, ms || 3000);
  }
  window.HC.toast = toast;

  /* ------------------------------------------- appearance studio v2 */
  var fab = document.createElement("button");
  fab.innerHTML = "\uD83C\uDFA8";
  fab.title = "Appearance";
  fab.style.cssText = "position:fixed;top:14px;right:14px;z-index:100000;" +
    "width:40px;height:40px;border:none;border-radius:13px;cursor:pointer;" +
    "color:#fff;font-size:17px;background:linear-gradient(135deg," +
    "rgba(124,92,255,.9),rgba(56,224,142,.85));box-shadow:0 8px 24px " +
    "rgba(0,0,0,.4)";
  document.body.appendChild(fab);
  var st = document.createElement("div");
  st.style.cssText = "position:fixed;top:62px;right:14px;z-index:100001;" +
    "width:292px;max-height:82vh;overflow-y:auto;display:none;" +
    "background:var(--surf);border:1px solid var(--bd);border-radius:18px;" +
    "padding:14px;backdrop-filter:blur(20px) saturate(1.4);color:var(--txt);" +
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
  function picker(val, fn, title) {
    var i = document.createElement("input");
    i.type = "color"; i.value = val || "#7c5cff";
    i.title = title || "empty = follow preset";
    i.style.cssText = "width:44px;height:28px;border:none;background:none;" +
      "cursor:pointer";
    i.oninput = function () { fn(i.value); };
    return i;
  }
  function clearBtn(fn) {
    var b = document.createElement("button");
    b.textContent = "auto";
    b.style.cssText = "font-size:10px;padding:3px 7px;border:1px solid " +
      "var(--bd);border-radius:7px;background:transparent;color:var(--sub);" +
      "cursor:pointer";
    b.onclick = fn;
    return b;
  }
  function section(txt2) {
    var h = document.createElement("div");
    h.textContent = txt2;
    h.style.cssText = "font-weight:800;letter-spacing:.1em;font-size:10px;" +
      "color:var(--sub);margin:12px 0 4px";
    return h;
  }
  function renderStudio() {
    st.innerHTML = "";
    st.appendChild(section("APPEARANCE"));
    var presets = document.createElement("div");
    presets.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin:8px 0";
    Object.keys(PRESETS).forEach(function (k) {
      var b = document.createElement("button");
      b.textContent = k;
      b.style.cssText = "padding:6px 11px;font-size:11px;font-weight:700;" +
        "cursor:pointer;border:1px solid " + (S.preset === k
          ? hexA(S.accent, .8) : "var(--bd)") + ";border-radius:9px;" +
        "background:" + (S.preset === k ? hexA(S.accent, .25) :
          "transparent") + ";color:var(--txt)";
      b.onclick = function () { S.preset = k; apply(true); renderStudio(); };
      presets.appendChild(b);
    });
    st.appendChild(presets);
    var ac = picker(S.accent, function (v) { S.accent = v; apply(); });
    st.appendChild(row("Accent", ac));
    var ac2 = picker(S.accent2, function (v) { S.accent2 = v; apply(); });
    st.appendChild(row("Secondary accent", ac2));
    var bgw = document.createElement("div");
    bgw.style.cssText = "display:flex;gap:6px;align-items:center;flex:1";
    bgw.appendChild(picker(S.bgColor, function (v) {
      S.bgColor = v; apply(); }, "background tint"));
    bgw.appendChild(clearBtn(function () {
      S.bgColor = ""; apply(); renderStudio(); }));
    st.appendChild(row("Background tint", bgw));
    var sfw = document.createElement("div");
    sfw.style.cssText = "display:flex;gap:6px;align-items:center;flex:1";
    sfw.appendChild(picker(S.surfColor, function (v) {
      S.surfColor = v; apply(); }, "surface tint"));
    sfw.appendChild(clearBtn(function () {
      S.surfColor = ""; apply(); renderStudio(); }));
    st.appendChild(row("Surface tint", sfw));
    var txw = document.createElement("div");
    txw.style.cssText = "display:flex;gap:6px;align-items:center;flex:1";
    txw.appendChild(picker(S.txtColor, function (v) {
      S.txtColor = v; apply(); }, "text color"));
    txw.appendChild(clearBtn(function () {
      S.txtColor = ""; apply(); renderStudio(); }));
    st.appendChild(row("Text color", txw));
    st.appendChild(row("Transparency",
      slider(40, 100, 1, Math.round(S.alpha * 100),
        function (v) { S.alpha = v / 100; apply(); })));
    st.appendChild(row("Corner radius",
      slider(0, 26, 1, S.radius, function (v) { S.radius = v; apply(); })));
    st.appendChild(row("Animation speed",
      slider(0.4, 2, 0.05, S.motion,
        function (v) { S.motion = v; apply(); })));
    st.appendChild(row("Motion intensity",
      slider(0.5, 2, 0.05, S.shadow,
        function (v) { S.shadow = v; apply(); })));
    st.appendChild(row("Blur strength",
      slider(0, 34, 1, S.blur, function (v) { S.blur = v; apply(); })));
    st.appendChild(row("Font size",
      slider(12, 18, 0.5, S.font, function (v) { S.font = v; apply(); })));
    st.appendChild(row("UI density",
      slider(0.85, 1.3, 0.05, S.density,
        function (v) { S.density = v; apply(); })));
    function tgl(label, key) {
      var i = document.createElement("input");
      i.type = "checkbox"; i.checked = !!S[key];
      i.onchange = function () {
        S[key] = i.checked; apply(); renderStudio();
        if (key === "sounds" && S.sounds) tone(1318.5, .1, .04);
      };
      return row(label, i);
    }
    st.appendChild(tgl("Reduced motion", "reduced"));
    st.appendChild(tgl("High contrast", "contrast"));
    st.appendChild(tgl("UI sounds", "sounds"));
    st.appendChild(section("SAVED THEMES"));
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
        S = Object.assign({}, DEF, saved[n]);
        apply(true); renderStudio(); toast("Theme applied: " + n, "ok");
      };
      var del = document.createElement("button");
      del.textContent = "\u2715";
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
    sv.textContent = "\uFF0B Save current as theme";
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
      renderStudio(); toast("Theme saved", "ok");
    };
    st.appendChild(sv);
    var ex = document.createElement("button");
    ex.textContent = "\u2B07 Export theme";
    ex.style.cssText = "width:100%;margin-top:6px;padding:8px;font-size:11px;" +
      "cursor:pointer;border:1px solid var(--bd);border-radius:10px;" +
      "background:transparent;color:var(--txt)";
    ex.onclick = function () {
      var j = JSON.stringify(S);
      try { navigator.clipboard.writeText(j); } catch (e) {}
      var ta = document.getElementById("hcThemeIO");
      if (ta) ta.value = j;
      toast("Theme JSON copied to clipboard", "ok");
    };
    st.appendChild(ex);
    var ta = document.createElement("textarea");
    ta.id = "hcThemeIO";
    ta.placeholder = "Paste a theme JSON here and press Import...";
    ta.style.cssText = "width:100%;height:54px;margin-top:8px;font-size:10px;" +
      "border-radius:9px;border:1px solid var(--bd);background:" +
      "rgba(0,0,0,.25);color:var(--txt);padding:6px;box-sizing:border-box";
    st.appendChild(ta);
    var im = document.createElement("button");
    im.textContent = "\u2B06 Import theme";
    im.style.cssText = "width:100%;margin-top:6px;padding:8px;font-size:11px;" +
      "cursor:pointer;border:1px solid var(--bd);border-radius:10px;" +
      "background:transparent;color:var(--txt)";
    im.onclick = function () {
      try {
        var obj = JSON.parse(ta.value);
        S = Object.assign({}, DEF, obj);
        apply(true); renderStudio(); toast("Theme imported", "ok");
      } catch (e) { toast("Invalid theme JSON", "err"); }
    };
    st.appendChild(im);
    var rst = document.createElement("button");
    rst.textContent = "Reset to defaults";
    rst.style.cssText = "width:100%;margin-top:6px;padding:8px;font-size:11px;" +
      "cursor:pointer;border:1px solid var(--bd);border-radius:10px;" +
      "background:transparent;color:var(--sub)";
    rst.onclick = function () {
      S = Object.assign({}, DEF); apply(true); renderStudio();
    };
    st.appendChild(rst);
  }

  /* ------------------------------- completion chime via snapshots */
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
              d.__hcChimed = true;
              if (S.sounds) toast(d.clips.length +
                " clips ready - review studio opened", "ok", 2600);
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
