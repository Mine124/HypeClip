/* HypeClip Review Studio - compare rows, shorts grid, preview modal,
   AI effect toggle panel, face-region picker. Single file, no deps. */
(function () {
  if (window.__hcReviewLoaded) return;
  window.__hcReviewLoaded = true;

  var JOB = null, LASTID = null, VIEW = "compare", SORT = "ret";
  var OPEN = false, modalClip = null, modalVersion = "edited";
  var customUrl = null, customFile = null;
  var faceAsked = {}, autoOpened = {}, faceLockedMsg = false;
  var thumbs = new Map(), tstate = new Map(), tq = [], tact = 0;
  var MAXC = 2, lastSig = "", io = null;

  var css = [
    ".hrvbtn{position:fixed;left:50%;transform:translateX(-50%);bottom:18px;",
    "z-index:99996;display:none;align-items:center;gap:8px;padding:10px 18px;",
    "border:none;border-radius:999px;cursor:pointer;color:#fff;",
    "font:800 12px/1 -apple-system,'Segoe UI',Roboto,sans-serif;",
    "letter-spacing:.08em;background:linear-gradient(90deg,#7c5cff,#38e08e);",
    "box-shadow:0 8px 30px rgba(124,92,255,.45)}",
    ".hrvbtn:hover{filter:brightness(1.15)}",
    ".hrv{position:fixed;inset:0;z-index:99999;display:none;",
    "background:rgba(8,10,20,.74);backdrop-filter:blur(14px);color:#e8ecff;",
    "font:13px/1.45 -apple-system,'Segoe UI',Roboto,sans-serif}",
    ".hrv.open{display:block}",
    ".hrv-h{display:flex;align-items:center;gap:12px;padding:14px 20px}",
    ".hrv-t{font-weight:800;letter-spacing:.1em;font-size:12px;color:#cfd6ff}",
    ".hrv-c{font-size:12px;color:#9aa3c7}",
    ".hrv-seg{display:flex;border:1px solid rgba(255,255,255,.16);",
    "border-radius:9px;overflow:hidden;margin-left:auto}",
    ".hrv-seg button{background:none;border:none;color:#9aa3c7;padding:7px 14px;",
    "cursor:pointer;font:700 11px/1 inherit;letter-spacing:.06em}",
    ".hrv-seg button.on{background:rgba(124,92,255,.35);color:#fff}",
    ".hrv-sel{background:rgba(255,255,255,.07);color:#e8ecff;border:1px solid",
    " rgba(255,255,255,.15);border-radius:8px;padding:6px 10px;font-size:12px}",
    ".hrv-x{background:rgba(255,255,255,.08);border:none;color:#fff;width:34px;",
    "height:34px;border-radius:10px;cursor:pointer;font-size:15px}",
    ".hrv-x:hover{background:rgba(255,93,93,.35)}",
    ".hrv-body{height:calc(100% - 62px);overflow-y:auto;padding:4px 20px 90px;",
    "max-width:1500px;margin:0 auto}",
    /* compare rows */
    ".hrv-row{display:grid;grid-template-columns:250px 1fr 1fr;gap:14px;",
    "background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);",
    "border-radius:16px;padding:14px;margin-bottom:14px;align-items:stretch}",
    ".hrv-meta{display:flex;flex-direction:column;gap:8px;min-width:0}",
    ".hrv-rank{font:800 11px/1 inherit;color:#fff;background:rgba(124,92,255,.5);",
    "padding:4px 9px;border-radius:8px;align-self:flex-start}",
    ".hrv-mth{width:100%;aspect-ratio:9/16;max-height:230px;object-fit:cover;",
    "border-radius:12px;background:#131828;cursor:pointer}",
    ".hrv-mt{font-weight:700;font-size:12px;overflow:hidden;display:-webkit-box;",
    "-webkit-line-clamp:2;-webkit-box-orient:vertical}",
    ".hrv-chips{display:flex;flex-wrap:wrap;gap:4px}",
    ".hrv-chip{font:700 10px/1 inherit;padding:4px 7px;border-radius:7px;",
    "background:rgba(255,255,255,.08);color:#cfd6ff}",
    ".hrv-chip b{font-weight:800}",
    ".hrv-col{position:relative;border-radius:14px;overflow:hidden;cursor:",
    "pointer;background:#10141f;min-height:230px;border:1px solid rgba(255,255,255,.07)}",
    ".hrv-col:hover{border-color:rgba(124,92,255,.6)}",
    ".hrv-col img{position:absolute;inset:0;width:100%;height:100%;",
    "object-fit:cover;opacity:.94}",
    ".hrv-tag{position:absolute;top:8px;left:8px;font:800 10px/1 inherit;",
    "padding:4px 8px;border-radius:7px;z-index:2}",
    ".hrv-tag.src{background:rgba(0,0,0,.6);color:#cfd6ff}",
    ".hrv-tag.ai{background:linear-gradient(90deg,#7c5cff,#38e08e);color:#fff}",
    ".hrv-play{position:absolute;inset:0;display:flex;align-items:center;",
    "justify-content:center;font-size:34px;color:rgba(255,255,255,.85);",
    "text-shadow:0 2px 12px #000;z-index:1;pointer-events:none}",
    ".hrv-no{position:absolute;inset:0;display:flex;align-items:center;",
    "justify-content:center;color:#5a628a;font-size:12px;text-align:center;",
    "padding:12px}",
    ".hrv-dl{position:absolute;bottom:8px;right:8px;z-index:3;width:32px;",
    "height:32px;border:none;border-radius:9px;cursor:pointer;font-size:14px;",
    "color:#fff;background:rgba(124,92,255,.9);opacity:0;transition:opacity .15s}",
    ".hrv-col:hover .hrv-dl{opacity:1}",
    /* grid */
    ".hrv-grid{display:grid;grid-template-columns:repeat(auto-fill,",
    "minmax(170px,1fr));gap:14px}",
    ".hrv-card{position:relative;aspect-ratio:9/16;border-radius:14px;",
    "overflow:hidden;cursor:pointer;background:#131828;",
    "outline:1px solid rgba(255,255,255,.07);transition:transform .16s,",
    "box-shadow .16s}",
    ".hrv-card:hover{transform:scale(1.035);z-index:2;box-shadow:0 14px 40px",
    " rgba(0,0,0,.55),0 0 0 2px rgba(124,92,255,.55)}",
    ".hrv-card img{position:absolute;inset:0;width:100%;height:100%;",
    "object-fit:cover}",
    ".hrv-ph{position:absolute;inset:0;display:flex;align-items:center;",
    "justify-content:center;font-size:30px;color:#3a4160;",
    "background:linear-gradient(160deg,#1a2038,#10141f)}",
    ".hrv-scrim{position:absolute;left:0;right:0;bottom:0;height:44%;",
    "background:linear-gradient(transparent,rgba(0,0,0,.82))}",
    ".hrv-num{position:absolute;top:8px;left:9px;font:800 10px/1 inherit;",
    "color:#fff;background:rgba(0,0,0,.55);padding:4px 7px;border-radius:7px}",
    ".hrv-dur{position:absolute;bottom:8px;right:9px;font:700 10px/1 inherit;",
    "color:#fff;background:rgba(0,0,0,.65);padding:4px 6px;border-radius:6px}",
    ".hrv-nm{position:absolute;bottom:8px;left:9px;right:52px;font:600 11px/1.3",
    " inherit;color:#fff;text-shadow:0 1px 4px #000;overflow:hidden;display:",
    "-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}",
    ".hrv-bd{position:absolute;top:8px;right:9px;display:flex;gap:4px;z-index:2}",
    ".hrv-b{font:800 9.5px/1 inherit;padding:3px 6px;border-radius:6px;",
    "color:#fff;background:rgba(0,0,0,.55)}",
    ".hrv-cdl{position:absolute;top:34px;right:9px;z-index:3;width:30px;",
    "height:30px;border:none;border-radius:9px;cursor:pointer;font-size:13px;",
    "color:#fff;background:rgba(124,92,255,.9);opacity:0;transition:opacity .15s;",
    "display:flex;align-items:center;justify-content:center;text-decoration:none}",
    ".hrv-card:hover .hrv-cdl{opacity:1}",
    /* modal */
    ".hrv-mod{position:fixed;inset:0;z-index:100000;display:none;",
    "align-items:center;justify-content:center;background:rgba(4,6,14,.82);",
    "backdrop-filter:blur(18px)}",
    ".hrv-mod.open{display:flex}",
    ".hrv-mw{display:flex;gap:14px;max-width:94vw;max-height:92vh;",
    "align-items:stretch}",
    ".hrv-mleft{width:min(92vw,400px);display:flex;flex-direction:column;",
    "gap:8px}",
    ".hrv-mv{width:100%;aspect-ratio:9/16;background:#000;border-radius:14px}",
    ".hrv-mc{display:flex;align-items:center;gap:7px;flex-wrap:wrap;color:#e8ecff;",
    "font-size:12px}",
    ".hrv-mc button{background:rgba(255,255,255,.1);border:none;color:#fff;",
    "width:30px;height:30px;border-radius:8px;cursor:pointer;font-size:12px}",
    ".hrv-mc button:hover{background:rgba(124,92,255,.5)}",
    ".hrv-seek{flex:1;min-width:100px;accent-color:#7c5cff}",
    ".hrv-vol{width:64px;accent-color:#7c5cff}",
    ".hrv-spd{background:rgba(255,255,255,.1);color:#fff;border:none;",
    "border-radius:7px;padding:4px;font-size:11px}",
    ".hrv-mrow{display:flex;align-items:center;gap:8px}",
    ".hrv-ver{display:flex;border:1px solid rgba(255,255,255,.16);",
    "border-radius:9px;overflow:hidden}",
    ".hrv-ver button{background:none;border:none;color:#9aa3c7;padding:6px 12px;",
    "cursor:pointer;font:700 11px/1 inherit}",
    ".hrv-ver button.on{background:rgba(124,92,255,.4);color:#fff}",
    ".hrv-dlb{padding:8px 14px;border:none;border-radius:10px;cursor:pointer;",
    "font:800 12px/1 inherit;color:#fff;",
    "background:linear-gradient(90deg,#7c5cff,#38e08e)}",
    ".hrv-dlb:hover{filter:brightness(1.15)}",
    ".hrv-ghost{background:rgba(255,255,255,.08);color:#c3c9e8;border:1px solid",
    " rgba(255,255,255,.14);border-radius:10px;padding:8px 12px;cursor:pointer;",
    "font:700 11px/1 inherit}",
    /* effect panel */
    ".hrv-fx{width:250px;background:rgba(17,21,38,.92);border:1px solid",
    " rgba(124,92,255,.3);border-radius:14px;padding:12px;overflow-y:auto}",
    ".hrv-fx h4{margin:0 0 8px;font:800 11px/1 inherit;letter-spacing:.09em;",
    "color:#cfd6ff}",
    ".hrv-fxr{display:flex;align-items:center;gap:8px;padding:5px 2px;",
    "font-size:12px;color:#e8ecff}",
    ".hrv-fxr input{accent-color:#7c5cff}",
    ".hrv-fxr span{flex:1}",
    ".hrv-fx-note{font-size:10.5px;color:#9aa3c7;margin-top:8px}",
    ".hrv-fx-busy{font-size:11px;color:#ffd166;margin-top:6px;display:none}",
    /* face picker */
    ".hrv-face{position:fixed;inset:0;z-index:100001;display:none;",
    "align-items:center;justify-content:center;flex-direction:column;gap:10px;",
    "background:rgba(4,6,14,.88);backdrop-filter:blur(16px);color:#e8ecff;",
    "font:13px/1.45 -apple-system,'Segoe UI',Roboto,sans-serif}",
    ".hrv-face.open{display:flex}",
    ".hrv-fw{position:relative;display:inline-block;line-height:0}",
    ".hrv-fw video{max-width:92vw;max-height:70vh;display:block;border-radius:",
    "10px}",
    ".hrv-rect{position:absolute;border:2px solid #38e08e;background:",
    "rgba(56,224,142,.14);cursor:move;box-shadow:0 0 0 9999px rgba(0,0,0,.45)}",
    ".hrv-hd{position:absolute;width:11px;height:11px;background:#38e08e;",
    "border:2px solid #0c2418;border-radius:3px}",
    ".hrv-coord{font:700 11px/1.5 ui-monospace,Consolas,monospace;color:#cfe9db;",
    "background:rgba(0,0,0,.5);padding:6px 10px;border-radius:8px}",
    ".hrv-face-h{display:flex;gap:8px;align-items:center}",
    ".hrv-face .hrv-dlb{font-size:12px;padding:9px 16px}",
    ".hrv-scrub{width:min(92vw,560px);accent-color:#38e08e}",
    /* toast */
    ".hrv-toast{position:fixed;top:16px;left:50%;transform:translateX(-50%);",
    "z-index:100002;background:rgba(17,21,38,.95);border:1px solid rgba(124,92,",
    "255,.4);color:#e8ecff;padding:10px 16px;border-radius:12px;font:600 12px/1.4",
    " -apple-system,'Segoe UI',Roboto,sans-serif;display:none;max-width:80vw}",
    ".hrv-empty{color:#9aa3c7;text-align:center;padding:60px 0}"
  ].join("");
  var st = document.createElement("style");
  st.textContent = css;
  document.head.appendChild(st);

  function el(t, c, h) {
    var e = document.createElement(t);
    if (c) e.className = c;
    if (h != null) e.innerHTML = h;
    return e;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;",
               '"': "&quot;" }[c];
    });
  }
  function fmtT(s) {
    s = Math.max(0, Math.round(Number(s) || 0));
    return (s >= 60 ? Math.floor(s / 60) + ":" : "") +
      String(s % 60).padStart(s >= 60 ? 2 : 1, "0");
  }
  function col(v) {
    v = Number(v) || 0;
    return v >= 86 ? "#38e08e" : v >= 78 ? "#ffd166" :
           v >= 68 ? "#ff9f43" : "#ff5d5d";
  }
  function toast(msg, ms) {
    var t = document.getElementById("hrvToast");
    if (!t) {
      t = el("div"); t.id = "hrvToast"; t.className = "hrv-toast";
      document.body.appendChild(t);
    }
    t.innerHTML = msg;
    t.style.display = "block";
    clearTimeout(t._tm);
    t._tm = setTimeout(function () { t.style.display = "none"; },
                       ms || 3200);
  }
  function cName(c) { return c.file || c.name || ""; }
  function cUrl(c) {
    return c.url || ("/clips/" + encodeURIComponent(cName(c)));
  }

  /* ---------------- launcher ---------------- */
  var btn = el("button", "hrvbtn", "🎬 REVIEW STUDIO <b>0</b>");
  document.body.appendChild(btn);
  btn.onclick = function () { OPEN = true; ov.classList.add("open"); render(); };

  /* ---------------- overlay ---------------- */
  var ov = el("div", "hrv");
  var head = el("div", "hrv-h");
  head.appendChild(el("span", "hrv-t", "REVIEW STUDIO"));
  var cnt = el("span", "hrv-c", "");
  head.appendChild(cnt);
  var seg = el("div", "hrv-seg");
  var bCmp = el("button", null, "COMPARE");
  var bGrd = el("button", null, "GRID");
  bCmp.onclick = function () { VIEW = "compare"; syncSeg(); render(); };
  bGrd.onclick = function () { VIEW = "grid"; syncSeg(); render(); };
  function syncSeg() {
    bCmp.className = VIEW === "compare" ? "on" : "";
    bGrd.className = VIEW === "grid" ? "on" : "";
  }
  seg.appendChild(bCmp); seg.appendChild(bGrd);
  head.appendChild(seg);
  var sel = el("select", "hrv-sel");
  [["ret", "Rank: retention"], ["viral", "Rank: viral score"],
   ["score", "Rank: hype score"], ["orig", "Order generated"],
   ["dur", "Shortest first"]].forEach(function (o) {
    var op = el("option", null, o[1]); op.value = o[0];
    if (o[0] === SORT) op.selected = true;
    sel.appendChild(op);
  });
  sel.onchange = function () { SORT = sel.value; render(); };
  head.appendChild(sel);
  var xb = el("button", "hrv-x", "✕");
  xb.onclick = function () { OPEN = false; ov.classList.remove("open"); };
  head.appendChild(xb);
  var body = el("div", "hrv-body");
  ov.appendChild(head); ov.appendChild(body);
  document.body.appendChild(ov);
  syncSeg();

  /* ---------------- thumbnails ---------------- */
  function tpump() {
    while (tact < MAXC && tq.length) {
      var j = tq.shift(); tact++;
      genThumb(j.file, j.url, function () { tact--; tpump(); });
    }
  }
  function genThumb(file, url, done) {
    var v = document.createElement("video");
    v.muted = true; v.preload = "auto"; v.src = url;
    var best = null, bestS = -1, cands = [], tries = 0;
    function fin() {
      try { v.removeAttribute("src"); v.load(); } catch (e) {}
      if (best) { thumbs.set(file, best); tstate.set(file, "done"); repaint(file); }
      else tstate.set(file, "fail");
      done();
    }
    v.onloadedmetadata = function () {
      var d = v.duration || 1;
      [0.28, 0.42, 0.56, 0.72].forEach(function (f) {
        var t = d * f;
        if (t > 0.2 && t < d - 0.2) cands.push(t);
      });
      cands.length ? nx() : fin();
    };
    v.onerror = fin;
    function nx() {
      if (!cands.length) { fin(); return; }
      try { v.currentTime = cands.shift(); } catch (e) { fin(); }
    }
    v.onseeked = function () {
      try {
        var cv = document.createElement("canvas");
        cv.width = 162; cv.height = 288;
        var g = cv.getContext("2d");
        g.drawImage(v, 0, 0, 162, 288);
        var d = g.getImageData(0, 0, 162, 288).data;
        var s1 = 0, s2 = 0, n = 0;
        for (var i = 0; i < d.length; i += 16) {
          var L = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
          s1 += L; s2 += L * L; n++;
        }
        var m = s1 / n, va = s2 / n - m * m;
        var sc = va - Math.abs(m - 110) * 1.5;
        if (sc > bestS) { bestS = sc; best = cv.toDataURL("image/jpeg", 0.72); }
      } catch (e) { fin(); return; }
      tries++;
      (tries >= 4 || !cands.length) ? fin() : nx();
    };
  }
  function repaint(file) {
    document.querySelectorAll('[data-tf="' + file.replace(/"/g, '\\"') + '"]')
      .forEach(function (im) { if (thumbs.get(file)) im.src = thumbs.get(file); });
  }
  function askThumb(card, file, url) {
    if (thumbs.get(file)) {
      var im = el("img"); im.src = thumbs.get(file);
      im.setAttribute("data-tf", file);
      card.insertBefore(im, card.firstChild);
      return;
    }
    if (tstate.get(file)) return;
    tstate.set(file, "queued");
    if (!io) io = new IntersectionObserver(function (es) {
      es.forEach(function (en) {
        if (!en.isIntersecting) return;
        var f = en.target.getAttribute("data-file");
        var u = en.target.getAttribute("data-url");
        io.unobserve(en.target);
        if (tstate.get(f) === "queued") {
          tstate.set(f, "pending");
          tq.push({ file: f, url: u }); tpump();
        }
      });
    }, { root: body, rootMargin: "300px" });
    card.setAttribute("data-file", file);
    card.setAttribute("data-url", url);
    io.observe(card);
  }

  /* ---------------- data ---------------- */
  function sorted() {
    var a = (JOB && JOB.clips || []).slice();
    if (SORT === "viral")
      a.sort(function (x, y) { return (y.viral || 0) - (x.viral || 0); });
    else if (SORT === "score")
      a.sort(function (x, y) { return (y.score || 0) - (x.score || 0); });
    else if (SORT === "ret")
      a.sort(function (x, y) {
        return ((y.retention || {}).score || 0) -
               ((x.retention || {}).score || 0);
      });
    else if (SORT === "dur")
      a.sort(function (x, y) { return (x.duration || 0) - (y.duration || 0); });
    return a;
  }
  function chips(c) {
    var h = '<span class="hrv-chip">⏱ <b>' + fmtT(c.duration) + "</b></span>";
    if (typeof c.viral === "number")
      h += '<span class="hrv-chip" style="color:' + col(c.viral) +
        '">🔥 <b>' + Math.round(c.viral) + "</b></span>";
    if (c.retention && typeof c.retention.score === "number")
      h += '<span class="hrv-chip" style="color:' + col(c.retention.score) +
        '">R <b>' + Math.round(c.retention.score) + "</b> " +
        esc(c.retention.grade || "") + "</span>";
    if (c.category)
      h += '<span class="hrv-chip">' + esc(c.category) + "</span>";
    if (c.created) h += '<span class="hrv-chip">' + esc(c.created) + "</span>";
    if (c.hook) h += '<span class="hrv-chip">🪝 ' + esc(c.hook) + "</span>";
    return h;
  }
  function cTitle(c) {
    var t = c.title || c.hook ||
      ((c.category ? c.category + " · " : "") + "clip");
    return t.length > 46 ? t.slice(0, 45) + "…" : t;
  }

  /* ---------------- compare view ---------------- */
  function posterCol(c, which, rank) {
    var isAI = which === "ai";
    var src = isAI ? cUrl(c) : (c.clean || "");
    var col = el("div", "hrv-col");
    col.appendChild(el("span", "hrv-tag " + (isAI ? "ai" : "src"),
      isAI ? "✨ AI EDITED" : "SOURCE (clean)"));
    var file = isAI ? cName(c) : (c.clean_file || cName(c));
    var ph = el("div", "hrv-ph", "🎬");
    col.appendChild(ph);
    askThumb(col, file, src || cUrl(c));
    col.appendChild(el("div", "hrv-play", "▶"));
    if (!src) {
      col.innerHTML = "";
      col.appendChild(el("span", "hrv-tag src", "SOURCE (clean)"));
      col.appendChild(el("div", "hrv-no",
        "no clean reference<br>(clip rendered before v4.2)"));
    }
    var a = el("a", "hrv-dl", "⬇");
    a.href = src || cUrl(c);
    a.download = (isAI ? cName(c) : (c.clean_file || "")) || "";
    a.title = "Download this version";
    a.onclick = function (e) { e.stopPropagation(); };
    col.appendChild(a);
    col.onclick = function () { openModal(c, isAI ? "edited" : "clean"); };
    return col;
  }
  function renderCompare() {
    var clips = sorted();
    body.innerHTML = "";
    if (!clips.length) {
      body.appendChild(el("div", "hrv-empty",
        "No clips yet - run a job and the review studio fills up."));
      return;
    }
    clips.forEach(function (c, i) {
      var row = el("div", "hrv-row");
      var meta = el("div", "hrv-meta");
      meta.appendChild(el("span", "hrv-rank",
        i === 0 ? "🏆 BEST" : "#" + (i + 1)));
      var th = el("img", "hrv-mth");
      th.onclick = function () { openModal(c, "edited"); };
      meta.appendChild(th);
      askThumb(th, cName(c), cUrl(c));
      meta.appendChild(el("div", "hrv-mt", esc(cTitle(c))));
      meta.appendChild(el("div", "hrv-chips", chips(c)));
      var rv = el("button", "hrv-ghost", "📁 folder");
      rv.onclick = function () {
        fetch("/api/reveal_clip", { method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ file: cName(c) }) });
      };
      meta.appendChild(rv);
      row.appendChild(meta);
      row.appendChild(posterCol(c, "src", i));
      row.appendChild(posterCol(c, "ai", i));
      body.appendChild(row);
    });
  }

  /* ---------------- grid view ---------------- */
  function renderGrid() {
    var clips = sorted();
    body.innerHTML = "";
    if (!clips.length) {
      body.appendChild(el("div", "hrv-empty", "No clips yet."));
      return;
    }
    var g = el("div", "hrv-grid");
    clips.forEach(function (c, i) {
      var card = el("div", "hrv-card");
      var ph = el("div", "hrv-ph", "🎬");
      card.appendChild(ph);
      askThumb(card, cName(c), cUrl(c));
      var bd = '<span class="hrv-b" style="color:' + col(c.viral || 0) +
        '">🔥' + Math.round(c.viral || 0) + "</span>";
      if (c.retention && typeof c.retention.score === "number")
        bd += '<span class="hrv-b" style="color:' +
          col(c.retention.score) + '">R' + Math.round(c.retention.score) +
          "</span>";
      card.insertAdjacentHTML("beforeend",
        '<div class="hrv-scrim"></div>' +
        '<span class="hrv-num">Clip #' + (i + 1) + "</span>" +
        '<div class="hrv-bd">' + bd + "</div>" +
        '<span class="hrv-dur">' + fmtT(c.duration) + "</span>" +
        '<span class="hrv-nm">' + esc(cTitle(c)) + "</span>");
      var a = el("a", "hrv-cdl", "⬇");
      a.href = cUrl(c); a.download = cName(c); a.title = "Download";
      a.onclick = function (e) { e.stopPropagation(); };
      card.appendChild(a);
      card.onclick = function () { openModal(c, "edited"); };
      g.appendChild(card);
    });
    body.appendChild(g);
  }

  function render() {
    if (!OPEN) return;
    var n = (JOB && JOB.clips || []).length;
    cnt.innerHTML = n + " clip" + (n === 1 ? "" : "s") +
      (JOB && JOB.face_rect ? " · 👤 face locked" : "");
    (VIEW === "compare" ? renderCompare : renderGrid)();
  }

  /* ---------------- modal + effect panel ---------------- */
  var mod = el("div", "hrv-mod");
  var mw = el("div", "hrv-mw");
  var ml = el("div", "hrv-mleft");
  var mv = el("video", "hrv-mv");
  mv.preload = "metadata"; mv.playsInline = true; mv.poster = "";
  ml.appendChild(mv);
  var mc = el("div", "hrv-mc");
  var bP = el("button", null, "▶");
  var tC = el("span", null, "0:00");
  var sk = el("input", "hrv-seek"); sk.type = "range";
  sk.min = 0; sk.max = 1000; sk.value = 0;
  var tT = el("span", null, "0:00");
  var bM = el("button", null, "🔊");
  var vl = el("input", "hrv-vol"); vl.type = "range";
  vl.min = 0; vl.max = 100; vl.value = 100;
  var sp = el("select", "hrv-spd");
  [0.5, 1, 1.5, 2].forEach(function (s) {
    var o = el("option", null, s + "×"); o.value = s;
    if (s === 1) o.selected = true;
    sp.appendChild(o);
  });
  var bF = el("button", null, "⛶");
  [bP, tC, sk, tT, bM, vl, sp, bF].forEach(function (n) { mc.appendChild(n); });
  ml.appendChild(mc);
  var mr = el("div", "hrv-mrow");
  var ver = el("div", "hrv-ver");
  var bSrc = el("button", null, "SOURCE");
  var bEd = el("button", null, "AI EDITED");
  ver.appendChild(bSrc); ver.appendChild(bEd);
  mr.appendChild(ver);
  var bDl = el("button", "hrv-dlb", "⬇ Download Clip");
  mr.appendChild(bDl);
  var bRv = el("button", "hrv-ghost", "📁");
  bRv.title = "Reveal in folder";
  mr.appendChild(bRv);
  ml.appendChild(mr);
  mw.appendChild(ml);
  var fxp = el("div", "hrv-fx");
  mw.appendChild(fxp);
  mod.appendChild(mw);
  document.body.appendChild(mod);
  fxp.style.display = "none";

  bP.onclick = function () { mv.paused ? mv.play() : mv.pause(); };
  mv.onplay = function () { bP.innerHTML = "⏸"; };
  mv.onpause = function () { bP.innerHTML = "▶"; };
  mv.ontimeupdate = function () {
    if (mv.duration) {
      sk.value = Math.round(mv.currentTime / mv.duration * 1000);
      tC.innerHTML = fmtT(mv.currentTime);
    }
  };
  mv.onloadedmetadata = function () { tT.innerHTML = fmtT(mv.duration); };
  sk.oninput = function () {
    if (mv.duration) mv.currentTime = sk.value / 1000 * mv.duration;
  };
  bM.onclick = function () {
    mv.muted = !mv.muted; bM.innerHTML = mv.muted ? "🔇" : "🔊";
  };
  vl.oninput = function () { mv.volume = vl.value / 100; };
  sp.onchange = function () { mv.playbackRate = parseFloat(sp.value); };
  bF.onclick = function () {
    if (document.fullscreenElement) document.exitFullscreen();
    else if (ml.requestFullscreen) ml.requestFullscreen();
  };
  bSrc.onclick = function () { setVersion("clean"); };
  bEd.onclick = function () { setVersion("edited"); };
  mod.onclick = function (e) { if (e.target === mod) closeModal(); };
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    if (mod.classList.contains("open")) { closeModal(); return; }
    if (faceOv.classList.contains("open")) { closeFace(); return; }
    if (OPEN) { OPEN = false; ov.classList.remove("open"); }
  });

  function srcFor(c, v) {
    if (v === "clean") return c.clean || cUrl(c);
    return customUrl || cUrl(c);
  }
  function setVersion(v) {
    if (!modalClip) return;
    modalVersion = v;
    customUrl = customUrl; // kept for edited
    var keep = mv.currentTime;
    var wasPlaying = !mv.paused;
    mv.src = srcFor(modalClip, v);
    mv.onloadedmetadata = function () {
      tT.innerHTML = fmtT(mv.duration);
      try { mv.currentTime = keep || 0; } catch (e) {}
      if (wasPlaying) mv.play().catch(function () {});
    };
    bSrc.className = v === "clean" ? "on" : "";
    bEd.className = v === "edited" ? "on" : "";
    var hasClean = !!modalClip.clean;
    bSrc.style.display = hasClean ? "" : "none";
    fxp.style.display = (v === "edited") ? "" : "none";
    if (v === "edited") loadFx();
    else fxp.innerHTML = "";
  }
  function openModal(c, v) {
    modalClip = c; customUrl = null; customFile = null;
    modalVersion = v || "edited";
    mv.src = srcFor(c, modalVersion);
    bSrc.className = modalVersion === "clean" ? "on" : "";
    bEd.className = modalVersion === "edited" ? "on" : "";
    bSrc.style.display = c.clean ? "" : "none";
    bDl.onclick = function () {
      var a = el("a");
      a.href = srcFor(c, modalVersion);
      a.download = (modalVersion === "edited" && customFile)
        ? customFile : cName(c);
      document.body.appendChild(a); a.click(); a.remove();
    };
    bRv.onclick = function () {
      fetch("/api/reveal_clip", { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file: cName(c) }) });
    };
    fxp.style.display = modalVersion === "edited" ? "" : "none";
    if (modalVersion === "edited") loadFx();
    mod.classList.add("open");
  }
  function closeModal() {
    mod.classList.remove("open");
    mv.pause(); mv.removeAttribute("src"); mv.load();
    modalClip = null; customUrl = null; customFile = null;
  }

  var FX = [["captions", "Captions"], ["zoom", "Punch-in Zooms"],
    ["shake", "Camera Shake"], ["glow", "Glow / Bloom"],
    ["grain", "Film Grain"], ["vignette", "Vignette"],
    ["sfx", "Sound Effects"], ["music", "Background Music"],
    ["flash", "Flash Intro"], ["beat", "Beat Sync"],
    ["title", "Title Badge"], ["progress", "Progress Bar"],
    ["watermark", "Watermark"], ["cta", "Subscribe CTA"],
    ["reframe", "Smart Reframe"]];
  var fxState = null, rrid = null;

  function loadFx() {
    fxp.innerHTML = "<h4>AI EFFECTS</h4>";
    if (!modalClip) return;
    fetch("/api/clip/plan?file=" + encodeURIComponent(cName(modalClip)))
      .then(function (r) {
        if (!r.ok) throw new Error("no plan");
        return r.json();
      })
      .then(function (d) {
        fxState = d.effects || {};
        fxp.innerHTML = "<h4>AI EFFECTS</h4>";
        FX.forEach(function (f) {
          var row = el("label", "hrv-fxr");
          var cb = el("input"); cb.type = "checkbox";
          cb.checked = !!fxState[f[0]];
          cb.disabled = !(f[0] in fxState) && fxState[f[0]] === undefined;
          cb.disabled = false;
          if (!(f[0] in fxState)) { row.style.opacity = ".4"; }
          cb.onchange = function () {
            fxState[f[0]] = cb.checked;
            runRerender();
          };
          row.appendChild(cb);
          row.appendChild(el("span", null, f[1]));
          fxp.appendChild(row);
        });
        var rst = el("button", "hrv-ghost", "↺ Reset to original");
        rst.style.marginTop = "8px";
        rst.onclick = function () {
          customUrl = null; customFile = null;
          setVersion("edited"); toast("Showing original AI edit");
        };
        fxp.appendChild(rst);
        fxp.appendChild(el("div", "hrv-fx-note",
          "Toggles re-render only this clip (fast). The preview and " +
          "download reflect the current switches."));
        var busy = el("div", "hrv-fx-busy");
        busy.id = "hrvFxBusy";
        fxp.appendChild(busy);
      })
      .catch(function () {
        fxp.innerHTML = "<h4>AI EFFECTS</h4>" +
          '<div class="hrv-fx-note">No saved plan for this clip (it was ' +
          "rendered before v4.2, or the temp source was cleaned up). " +
          "New clips will support per-effect toggles.</div>";
      });
  }
  function runRerender() {
    if (!modalClip || !fxState) return;
    var busy = document.getElementById("hrvFxBusy");
    if (busy) {
      busy.style.display = "block";
      busy.innerHTML = "⏳ Re-rendering clip with current switches...";
    }
    fxp.querySelectorAll("input").forEach(function (i) { i.disabled = true; });
    fetch("/api/clip/rerender", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file: cName(modalClip),
                             effects: fxState }) })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.rerender_id) throw new Error(d.detail || "failed");
        rrid = d.rerender_id;
        var poll = setInterval(function () {
          fetch("/api/rerender/" + rrid)
            .then(function (r) { return r.json(); })
            .then(function (s) {
              if (s.state === "running") return;
              clearInterval(poll);
              fxp.querySelectorAll("input")
                .forEach(function (i) { i.disabled = false; });
              if (busy) busy.style.display = "none";
              if (s.state !== "done") {
                toast("Re-render failed: " + (s.error || "unknown"), 5000);
                return;
              }
              customUrl = (s.result || {}).url;
              customFile = (s.result || {}).file;
              toast("✨ Custom version ready - preview + download updated");
              if (modalVersion === "edited") {
                var keep = mv.currentTime, wp = !mv.paused;
                mv.src = customUrl;
                mv.onloadedmetadata = function () {
                  tT.innerHTML = fmtT(mv.duration);
                  try { mv.currentTime = keep || 0; } catch (e) {}
                  if (wp) mv.play().catch(function () {});
                };
              }
            }).catch(function () { clearInterval(poll); });
        }, 1600);
      })
      .catch(function (e) {
        fxp.querySelectorAll("input")
          .forEach(function (i) { i.disabled = false; });
        if (busy) busy.style.display = "none";
        toast("Re-render failed: " + e.message, 5000);
      });
  }

  /* ---------------- face region picker ---------------- */
  var faceOv = el("div", "hrv-face");
  var fw = el("div", "hrv-fw");
  var fv = el("video");
  fv.muted = true; fv.playsInline = true; fv.preload = "metadata";
  fv.crossOrigin = "anonymous";
  fw.appendChild(fv);
  var rectEl = el("div", "hrv-rect");
  rectEl.style.display = "none";
  fw.appendChild(rectEl);
  var HANDLES = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
  HANDLES.forEach(function (d) {
    var h = el("div", "hrv-hd");
    h.setAttribute("data-d", d);
    rectEl.appendChild(h);
  });
  var coord = el("div", "hrv-coord",
    "drag on the video to draw the box over the streamer's face/camera");
  var frow = el("div", "hrv-face-h");
  var fLock = el("button", "hrv-dlb", "👤 LOCK FACE REGION");
  var fSkip = el("button", "hrv-ghost", "Skip this job");
  frow.appendChild(fLock); frow.appendChild(fSkip);
  var scrub = el("input", "hrv-scrub");
  scrub.type = "range"; scrub.min = 0; scrub.max = 1000; scrub.value = 0;
  faceOv.appendChild(el("div", null,
    '<b style="letter-spacing:.08em">FACE SELECTION WIZARD</b><br>' +
    '<span style="color:#9aa3c7;font-size:12px">Lock this BEFORE starting ' +
    "the scan below - the region applies to every clip in this job.</span>"));
  faceOv.appendChild(fw);
  faceOv.appendChild(scrub);
  faceOv.appendChild(coord);
  faceOv.appendChild(frow);
  document.body.appendChild(faceOv);

  var FR = null; // {x,y,w,h} normalized
  var faceJobId = null;

  fv.addEventListener("loadedmetadata", function () {
    scrub.max = Math.round((fv.duration || 1) * 1000);
  });
  scrub.oninput = function () {
    try { fv.currentTime = scrub.value / 1000; } catch (e) {}
  };
  function nbox() {
    var r = fw.getBoundingClientRect();
    return r;
  }
  function clampN(v) { return Math.max(0, Math.min(1, v)); }
  function drawR() {
    if (!FR) { rectEl.style.display = "none"; return; }
    rectEl.style.display = "block";
    rectEl.style.left = (FR.x * 100) + "%";
    rectEl.style.top = (FR.y * 100) + "%";
    rectEl.style.width = (FR.w * 100) + "%";
    rectEl.style.height = (FR.h * 100) + "%";
    var vw = fv.videoWidth || 1, vh = fv.videoHeight || 1;
    coord.innerHTML = "norm: x=" + FR.x.toFixed(3) + " y=" + FR.y.toFixed(3) +
      " w=" + FR.w.toFixed(3) + " h=" + FR.h.toFixed(3) +
      " &nbsp;|&nbsp; px: " + Math.round(FR.x * vw) + "," +
      Math.round(FR.y * vh) + " " + Math.round(FR.w * vw) + "×" +
      Math.round(FR.h * vh);
  }
  function evN(e) {
    var r = nbox();
    return { x: clampN((e.clientX - r.left) / r.width),
             y: clampN((e.clientY - r.top) / r.height) };
  }
  var drag = null;
  fw.addEventListener("mousedown", function (e) {
    if (e.target !== fw && e.target !== fv) return;
    var p = evN(e);
    drag = { mode: "new", sx: p.x, sy: p.y };
    FR = { x: p.x, y: p.y, w: 0.01, h: 0.01 };
    e.preventDefault();
  });
  rectEl.addEventListener("mousedown", function (e) {
    if (e.target.classList.contains("hrv-hd")) {
      drag = { mode: "resize", d: e.target.getAttribute("data-d"),
               o: Object.assign({}, FR), p: evN(e) };
    } else {
      drag = { mode: "move", o: Object.assign({}, FR), p: evN(e) };
    }
    e.preventDefault(); e.stopPropagation();
  });
  document.addEventListener("mousemove", function (e) {
    if (!drag) return;
    var p = evN(e);
    if (drag.mode === "new") {
      FR.x = Math.min(drag.sx, p.x); FR.y = Math.min(drag.sy, p.y);
      FR.w = Math.max(0.01, Math.abs(p.x - drag.sx));
      FR.h = Math.max(0.01, Math.abs(p.y - drag.sy));
    } else if (drag.mode === "move") {
      FR.x = clampN(drag.o.x + (p.x - drag.p.x));
      FR.y = clampN(drag.o.y + (p.y - drag.p.y));
    } else {
      var o = drag.o, dx = p.x - drag.p.x, dy = p.y - drag.p.y, d = drag.d;
      FR = Object.assign({}, o);
      if (d.indexOf("w") > -1) {
        FR.x = clampN(o.x + dx); FR.w = Math.max(0.02, o.w - dx);
      }
      if (d.indexOf("e") > -1) FR.w = Math.max(0.02, o.w + dx);
      if (d.indexOf("n") > -1) {
        FR.y = clampN(o.y + dy); FR.h = Math.max(0.02, o.h - dy);
      }
      if (d.indexOf("s") > -1) FR.h = Math.max(0.02, o.h + dy);
    }
    drawR();
  });
  document.addEventListener("mouseup", function () { drag = null; });

  fLock.onclick = function () {
    if (!FR || FR.w < 0.03 || FR.h < 0.03) {
      toast("Draw a box around the streamer's face/camera first");
      return;
    }
    fetch("/api/jobs/" + faceJobId + "/face", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rect: [FR.x, FR.y, FR.w, FR.h] }) })
      .then(function (r) { return r.json(); })
      .then(function () {
        closeFace();
        faceLockedMsg = true;
        toast("👤 Face region locked - facecam top, gameplay bottom for " +
              "every clip in this job");
      })
      .catch(function () { toast("Could not lock face region"); });
  };
  fSkip.onclick = function () { closeFace(); };
  function closeFace() { faceOv.classList.remove("open"); }
  function openFace(jobId, mediaUrl) {
    faceJobId = jobId;
    if (!fv.src || fv.getAttribute("data-job") !== jobId) {
      fv.src = mediaUrl;
      fv.setAttribute("data-job", jobId);
      FR = null; drawR();
    }
    faceOv.classList.add("open");
  }

  /* ---------------- snapshot capture + polling ---------------- */
  function updateJob(d) {
    JOB = d;
    LASTID = d.id;
    var n = (d.clips || []).length;
    btn.style.display = n ? "flex" : "none";
    btn.querySelector("b").innerHTML = n;
    if (d.state === "awaiting_selection" || d.stage === "awaiting_selection") {
      if (!d.face_rect && !faceAsked[d.id] && d.media_url) {
        faceAsked[d.id] = true;
        openFace(d.id, d.media_url);
      }
    }
    if (d.face_rect && !faceLockedMsg) {
      faceLockedMsg = true;
      closeFace();
    }
    if (d.state === "done" && n && !autoOpened[d.id]) {
      autoOpened[d.id] = true;
      OPEN = true; ov.classList.add("open");
    }
    var sig = d.id + ":" + n + ":" + VIEW + ":" + SORT +
      ":" + (d.face_rect ? 1 : 0);
    if (sig !== lastSig) { lastSig = sig; render(); }
  }
  var of = window.fetch;
  window.fetch = function () {
    var url = "";
    try {
      var a0 = arguments[0];
      url = typeof a0 === "string" ? a0 : (a0 && a0.url) || "";
    } catch (e) {}
    var p = of.apply(this, arguments);
    if (url.indexOf("/api/jobs/") > -1 && url.indexOf("/face") < 0) {
      p.then(function (resp) {
        try {
          resp.clone().json().then(function (d) {
            if (d && d.id && d.clips) updateJob(d);
          }).catch(function () {});
        } catch (e) {}
      }).catch(function () {});
    }
    return p;
  };
  setInterval(function () {
    if (!LASTID) return;
    of("/api/jobs/" + LASTID).then(function (r) { return r.json(); })
      .then(function (d) { if (d && d.id) updateJob(d); })
      .catch(function () {});
  }, 2500);

  render();
})();
