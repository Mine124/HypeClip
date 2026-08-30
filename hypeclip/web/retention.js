/* HypeClip Retention AI - floating panel. Auto-loads with the app. */
(function () {
  if (window.__hcRetentionLoaded) return;
  window.__hcRetentionLoaded = true;

  var JOB = null;
  var COLLAPSED = false;
  var OPEN = {};
  var lastSig = "";

  var css = [
    ".hcrt{position:fixed;right:18px;bottom:18px;z-index:99998;width:340px;",
    "font:13px/1.45 -apple-system,'Segoe UI',Roboto,sans-serif;color:#e8ecff;",
    "background:rgba(17,21,38,.92);border:1px solid rgba(124,92,255,.35);",
    "border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.5);",
    "backdrop-filter:blur(10px);overflow:hidden}",
    ".hcrt-h{display:flex;align-items:center;gap:8px;padding:10px 12px;",
    "cursor:move;background:linear-gradient(90deg,rgba(124,92,255,.25),",
    "rgba(124,92,255,.05));user-select:none}",
    ".hcrt-dot{width:9px;height:9px;border-radius:50%;background:#38e08e;",
    "box-shadow:0 0 10px #38e08e}",
    ".hcrt-t{font-weight:700;letter-spacing:.08em;font-size:11px;",
    "color:#cfd6ff}",
    ".hcrt-min{margin-left:auto;cursor:pointer;opacity:.7;font-size:14px;",
    "background:none;border:none;color:#e8ecff}",
    ".hcrt-b{max-height:52vh;overflow:auto;padding:6px 10px 10px}",
    ".hcrt-sum{display:flex;gap:8px;margin:6px 0}",
    ".hcrt-chip{flex:1;background:rgba(255,255,255,.05);border-radius:10px;",
    "padding:8px;text-align:center}",
    ".hcrt-chip b{display:block;font-size:18px}",
    ".hcrt-chip span{font-size:10px;color:#9aa3c7;text-transform:uppercase;",
    "letter-spacing:.08em}",
    ".hcrt-row{margin:8px 0;border:1px solid rgba(255,255,255,.08);",
    "border-radius:10px;padding:8px;background:rgba(255,255,255,.03);",
    "cursor:pointer}",
    ".hcrt-rhead{display:flex;align-items:center;gap:8px}",
    ".hcrt-name{font-weight:600;font-size:12px;overflow:hidden;",
    "text-overflow:ellipsis;white-space:nowrap;flex:1}",
    ".hcrt-badge{font-weight:800;font-size:15px;padding:2px 8px;",
    "border-radius:8px}",
    ".hcrt-grade{font-size:10px;font-weight:800;padding:2px 6px;",
    "border-radius:6px}",
    ".hcrt-cv{width:100%;height:30px;margin-top:6px;display:block}",
    ".hcrt-det{display:none;margin-top:6px}",
    ".hcrt-row.open .hcrt-det{display:block}",
    ".hcrt-verdict{color:#9aa3c7;font-size:11px;margin-top:4px}",
    ".hcrt-risk{margin:4px 0;padding:6px 8px;border-radius:8px;",
    "background:rgba(255,93,93,.08);border:1px solid rgba(255,93,93,.18)}",
    ".hcrt-risk b{font-size:11px}",
    ".hcrt-risk div{font-size:11px;color:#c3c9e8}",
    ".hcrt-btn{margin-top:6px;margin-right:6px;padding:5px 10px;",
    "border-radius:8px;border:1px solid rgba(124,92,255,.5);",
    "background:rgba(124,92,255,.18);color:#e8ecff;cursor:pointer;",
    "font-weight:700;font-size:11px}",
    ".hcrt-btn:hover{background:rgba(124,92,255,.35)}",
    ".hcrt-ok{color:#38e08e;font-size:11px;font-weight:700;margin-top:4px}",
    ".hcrt-busy{color:#ffd166;font-size:11px;margin-top:4px}",
    ".hcrt-empty{color:#9aa3c7;font-size:11px;padding:8px;text-align:center}"
  ].join("");

  var st = document.createElement("style");
  st.textContent = css;
  document.head.appendChild(st);

  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;",
               '"': "&quot;" }[c];
    });
  }
  function colorFor(score) {
    if (score >= 86) return "#38e08e";
    if (score >= 78) return "#ffd166";
    if (score >= 68) return "#ff9f43";
    return "#ff5d5d";
  }
  function clipName(c) { return c.file || c.name || "clip"; }

  var box = el("div", "hcrt");
  var head = el("div", "hcrt-h",
    '<span class="hcrt-dot"></span><span class="hcrt-t">RETENTION AI</span>');
  var minBtn = el("button", "hcrt-min", "-");
  head.appendChild(minBtn);
  var body = el("div", "hcrt-b");
  box.appendChild(head);
  box.appendChild(body);
  document.body.appendChild(box);
  minBtn.onclick = function () {
    COLLAPSED = !COLLAPSED;
    body.style.display = COLLAPSED ? "none" : "";
    minBtn.innerHTML = COLLAPSED ? "+" : "-";
  };
  (function () {
    var dx = 0, dy = 0, down = false;
    head.addEventListener("mousedown", function (e) {
      down = true;
      dx = e.clientX - box.offsetLeft;
      dy = e.clientY - box.offsetTop;
      e.preventDefault();
    });
    document.addEventListener("mousemove", function (e) {
      if (!down) return;
      box.style.left = (e.clientX - dx) + "px";
      box.style.top = (e.clientY - dy) + "px";
      box.style.right = "auto";
      box.style.bottom = "auto";
    });
    document.addEventListener("mouseup", function () { down = false; });
  })();

  function sparkline(cv, curve) {
    var w = cv.width = 300, h = cv.height = 60;
    var g = cv.getContext("2d");
    g.clearRect(0, 0, w, h);
    if (!curve || curve.length < 2) return;
    var t0 = curve[0][0], t1 = curve[curve.length - 1][0] || 1;
    g.beginPath();
    for (var i = 0; i < curve.length; i++) {
      var x = ((curve[i][0] - t0) / Math.max(0.001, t1 - t0)) * (w - 4) + 2;
      var y = h - 4 - (curve[i][1] / 100) * (h - 8);
      if (i) g.lineTo(x, y); else g.moveTo(x, y);
    }
    g.strokeStyle = "#7c5cff";
    g.lineWidth = 2.5;
    g.stroke();
    g.lineTo(w - 2, h);
    g.lineTo(2, h);
    g.closePath();
    g.fillStyle = "rgba(124,92,255,.12)";
    g.fill();
  }

  function render(force) {
    var sig = JOB ? (JOB.id + ":" + (JOB.clips || []).map(function (c) {
      return clipName(c) + ":" + (c.retention ? c.retention.score : "-");
    }).join("|")) : "";
    if (!force && sig === lastSig) return;
    lastSig = sig;
    if (!JOB) {
      body.innerHTML = '<div class="hcrt-empty">Paste a link and generate ' +
        'clips - retention predictions appear here.</div>';
      return;
    }
    var withR = (JOB.clips || []).filter(function (c) { return c.retention; });
    if (!withR.length) {
      body.innerHTML = '<div class="hcrt-empty">No retention data yet - ' +
        'scores appear as clips finish rendering.</div>';
      return;
    }
    body.innerHTML = "";
    var avg = Math.round(withR.reduce(function (a, c) {
      return a + c.retention.score; }, 0) / withR.length);
    var best = withR.reduce(function (a, c) {
      return (c.retention.score > a.retention.score ? c : a); }, withR[0]);
    body.appendChild(el("div", "hcrt-sum",
      '<div class="hcrt-chip"><b style="color:' + colorFor(avg) + '">' +
      avg + '</b><span>avg score</span></div>' +
      '<div class="hcrt-chip"><b style="color:' +
      colorFor(best.retention.score) + '">' + best.retention.score +
      '</b><span>best clip</span></div>' +
      '<div class="hcrt-chip"><b>' + withR.length +
      '</b><span>graded</span></div>'));
    (JOB.clips || []).forEach(function (c) {
      var r = c.retention;
      if (!r) return;
      var name = clipName(c);
      var row = el("div", "hcrt-row" + (OPEN[name] ? " open" : ""));
      row.appendChild(el("div", "hcrt-rhead",
        '<span class="hcrt-badge" style="color:' + colorFor(r.score) + '">' +
        r.score + '</span>' +
        '<span class="hcrt-grade" style="background:' + colorFor(r.score) +
        '22;color:' + colorFor(r.score) + '">' + esc(r.grade) + '</span>' +
        '<span class="hcrt-name" title="' + esc(name) + '">' +
        esc(name) + '</span>'));
      var cv = el("canvas", "hcrt-cv");
      row.appendChild(cv);
      row.appendChild(el("div", "hcrt-verdict",
        esc(r.verdict) + " - completion " + r.completion +
        "% - watch " + Math.round(r.watch_time) + "s"));
      var det = el("div", "hcrt-det");
      (r.risks || []).forEach(function (rk) {
        det.appendChild(el("div", "hcrt-risk",
          "<b>" + esc(rk.kind) + " - " + esc(rk.reason) + "</b>" +
          "<div>FIX: " + esc(rk.fix) + "</div>"));
      });
      if (!(r.risks || []).length) {
        det.appendChild(el("div", "hcrt-ok",
          "No drop risks found - export as is."));
      }
      var bImp = el("button", "hcrt-btn", "AUTO-IMPROVE (V2)");
      bImp.onclick = function (e) { e.stopPropagation(); improve(c, bImp); };
      var bFolder = el("button", "hcrt-btn", "SHOW IN FOLDER");
      bFolder.onclick = function (e) {
        e.stopPropagation();
        fetch("/api/reveal_clip", { method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ file: name }) });
      };
      det.appendChild(bImp);
      det.appendChild(bFolder);
      row.appendChild(det);
      row.onclick = function (e) {
        if (e.target.tagName === "BUTTON") return;
        OPEN[name] = !OPEN[name];
        row.classList.toggle("open");
      };
      body.appendChild(row);
      sparkline(cv, r.curve);
    });
  }

  function improve(clip, btn) {
    btn.disabled = true;
    var name = clipName(clip);
    var note = el("div", "hcrt-busy", "Analyzing and rendering V2...");
    btn.parentNode.appendChild(note);
    fetch("/api/clip/revise", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file: name }) })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var id = d.revise_id;
        var poll = setInterval(function () {
          fetch("/api/revise/" + id)
            .then(function (r) { return r.json(); })
            .then(function (s) {
              if (s.state === "running") return;
              clearInterval(poll);
              if (s.state !== "done") {
                note.className = "hcrt-busy";
                note.textContent = "V2 failed: " + (s.error || "unknown");
                return;
              }
              var res = s.result || {};
              if (res.improved) {
                note.className = "hcrt-ok";
                note.textContent = "V2 ready - retention " +
                  res.report_v1.score + " -> " + res.report_v2.score +
                  " (" + res.file + ")";
                clip.retention = res.report_v2;
                if (res.file) clip.file = res.file;
                render(true);
              } else {
                note.className = "hcrt-ok";
                note.textContent = "V2 scored " +
                  ((res.report_v2 || {}).score || "?") + " - V1 " +
                  ((res.report_v1 || {}).score) +
                  " is already the strongest version.";
              }
            }).catch(function () {});
        }, 1500);
      }).catch(function () {
        note.textContent = "Could not start revision.";
      });
  }

  var of = window.fetch;
  window.fetch = function () {
    var url = "";
    try {
      var a0 = arguments[0];
      url = typeof a0 === "string" ? a0 : (a0 && a0.url) || "";
    } catch (e) {}
    var p = of.apply(this, arguments);
    if (url.indexOf("/api/jobs/") > -1) {
      p.then(function (resp) {
        try {
          resp.clone().json().then(function (d) {
            if (d && d.clips) { JOB = d; render(); }
          }).catch(function () {});
        } catch (e) {}
      }).catch(function () {});
    }
    return p;
  };

  render();
})();
