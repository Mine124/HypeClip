/* HypeClip VRE - Viral Reverse Engineering panel (bottom-left). */
(function () {
  if (window.__hcVreLoaded) return;
  window.__hcVreLoaded = true;

  var css = [
    ".hcvre{position:fixed;left:18px;bottom:18px;z-index:99998;width:350px;",
    "font:13px/1.45 -apple-system,'Segoe UI',Roboto,sans-serif;color:#e8ecff;",
    "background:rgba(17,21,38,.92);border:1px solid rgba(56,224,142,.3);",
    "border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.5);",
    "backdrop-filter:blur(10px);overflow:hidden}",
    ".hcvre-h{display:flex;align-items:center;gap:8px;padding:10px 12px;",
    "cursor:move;background:linear-gradient(90deg,rgba(56,224,142,.22),",
    "rgba(56,224,142,.04));user-select:none}",
    ".hcvre-t{font-weight:800;letter-spacing:.1em;font-size:11px;color:#cfe9db}",
    ".hcvre-min{margin-left:auto;cursor:pointer;background:none;border:none;",
    "color:#e8ecff;font-size:14px;opacity:.7}",
    ".hcvre-b{max-height:56vh;overflow:auto;padding:10px 12px 12px}",
    ".hcvre-lab{font-size:10px;letter-spacing:.08em;color:#9aa3c7;",
    "text-transform:uppercase;margin:8px 0 4px}",
    ".hcvre-in{width:100%;box-sizing:border-box;background:rgba(255,255,255,.06);",
    "border:1px solid rgba(255,255,255,.12);border-radius:8px;color:#e8ecff;",
    "padding:8px;font-size:12px}",
    ".hcvre-row{display:flex;gap:8px;align-items:center;margin-top:8px}",
    ".hcvre-go{padding:7px 12px;border-radius:8px;border:none;cursor:pointer;",
    "font-weight:800;font-size:11px;color:#0c2418;",
    "background:linear-gradient(90deg,#38e08e,#7c5cff);flex:1}",
    ".hcvre-go:disabled{opacity:.5}",
    ".hcvre-chk{font-size:11px;color:#c3c9e8;display:flex;gap:5px;",
    "align-items:center}",
    ".hcvre-bar{height:6px;background:rgba(255,255,255,.08);border-radius:3px;",
    "overflow:hidden;margin-top:8px;display:none}",
    ".hcvre-bar i{display:block;height:100%;width:0;",
    "background:linear-gradient(90deg,#38e08e,#7c5cff)}",
    ".hcvre-msg{font-size:11px;color:#ffd166;margin-top:6px;display:none}",
    ".hcvre-bp{border:1px solid rgba(255,255,255,.1);border-radius:10px;",
    "padding:8px;margin-top:8px;background:rgba(255,255,255,.03)}",
    ".hcvre-bpn{font-weight:700;font-size:12px;overflow:hidden;",
    "text-overflow:ellipsis;white-space:nowrap}",
    ".hcvre-chips{display:flex;gap:4px;flex-wrap:wrap;margin-top:5px}",
    ".hcvre-chip{font-size:9.5px;font-weight:700;letter-spacing:.04em;",
    "padding:2px 7px;border-radius:6px;background:rgba(124,92,255,.18);",
    "color:#cfd6ff;text-transform:uppercase}",
    ".hcvre-why{font-size:11px;color:#bfc7ea;margin:6px 0 2px;",
    "padding-left:14px}",
    ".hcvre-why li{margin:3px 0}",
    ".hcvre-btn{margin-top:6px;margin-right:6px;padding:5px 10px;",
    "border-radius:8px;border:1px solid rgba(56,224,142,.5);",
    "background:rgba(56,224,142,.14);color:#d9ffe9;cursor:pointer;",
    "font-weight:700;font-size:11px}",
    ".hcvre-btn.gray{border-color:rgba(255,255,255,.2);color:#c3c9e8;",
    "background:rgba(255,255,255,.05)}",
    ".hcvre-btn:hover{filter:brightness(1.25)}",
    ".hcvre-on{display:flex;align-items:center;gap:8px;margin-top:8px;",
    "padding:8px;border-radius:10px;background:rgba(56,224,142,.12);",
    "border:1px solid rgba(56,224,142,.35);font-size:11px}",
    ".hcvre-dot{width:8px;height:8px;border-radius:50%;background:#38e08e;",
    "box-shadow:0 0 8px #38e08e}",
    ".hcvre-empty{color:#9aa3c7;font-size:11px;padding:6px 2px}"
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

  var box = el("div", "hcvre");
  var head = el("div", "hcvre-h",
    '<span class="hcvre-dot"></span><span class="hcvre-t">VIRAL REVERSE ENGINEER</span>');
  var min = el("button", "hcvre-min", "-");
  head.appendChild(min);
  var body = el("div", "hcvre-b");
  box.appendChild(head); box.appendChild(body);
  document.body.appendChild(box);
  min.onclick = function () {
    body.style.display = body.style.display === "none" ? "" : "none";
    min.innerHTML = body.style.display === "none" ? "+" : "-";
  };
  (function () {
    var dx = 0, dy = 0, down = false;
    head.addEventListener("mousedown", function (e) {
      down = true; dx = e.clientX - box.offsetLeft;
      dy = e.clientY - box.offsetTop; e.preventDefault();
    });
    document.addEventListener("mousemove", function (e) {
      if (!down) return;
      box.style.left = (e.clientX - dx) + "px";
      box.style.top = (e.clientY - dy) + "px";
    });
    document.addEventListener("mouseup", function () { down = false; });
  })();

  var urlIn = el("input", "hcvre-in");
  urlIn.placeholder = "Paste a viral video URL (YouTube / TikTok / Reel)...";
  var deep = el("label", "hcvre-chk",
    '<input type="checkbox"> deep analysis (transcribes hook)');
  var go = el("button", "hcvre-go", "ANALYZE EDITING STYLE");
  var bar = el("div", "hcvre-bar", "<i></i>");
  var msg = el("div", "hcvre-msg");
  var activeBox = el("div");
  var list = el("div");

  body.appendChild(el("div", "hcvre-lab", "1 - Deconstruct a viral video"));
  body.appendChild(urlIn);
  var row = el("div", "hcvre-row");
  row.appendChild(go); row.appendChild(deep);
  body.appendChild(row); body.appendChild(bar); body.appendChild(msg);
  body.appendChild(el("div", "hcvre-lab", "2 - Activate a blueprint"));
  body.appendChild(activeBox);
  body.appendChild(list);

  var chips = function (p) {
    if (!p) return "";
    return ["pace: " + p.pace, "camera: " + p.camera,
            "captions: " + p.captions, "sfx: " + p.sfx,
            "audio: " + p.audio].map(function (x) {
      return '<span class="hcvre-chip">' + esc(x) + "</span>";
    }).join("");
  };

  function bpCard(bp, expanded) {
    var d = el("div", "hcvre-bp");
    d.appendChild(el("div", "hcvre-bpn", esc(bp.name || bp.title)));
    d.appendChild(el("div", "hcvre-chips", chips(bp.profile)));
    var acts = el("div");
    var use = el("button", "hcvre-btn",
      activeId === bp.id ? "RE-ACTIVATE" : "USE FOR NEXT JOB");
    use.onclick = function (e) {
      e.stopPropagation();
      fetch("/api/vre/activate", { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: bp.id }) })
        .then(load);
    };
    acts.appendChild(use);
    if (bp.id) {
      var view = el("button", "hcvre-btn gray", expanded ? "HIDE WHY" : "WHY IT WORKS");
      view.onclick = function (e) {
        e.stopPropagation();
        fetch("/api/vre/blueprint/" + bp.id)
          .then(function (r) { return r.json(); })
          .then(function (full) {
            var w = d.querySelector(".hcvre-whywrap");
            if (w) { w.remove(); return; }
            var wrap = el("div", "hcvre-whywrap", "<ul class='hcvre-why'>" +
              (full.why || []).map(function (x) {
                return "<li>" + esc(x) + "</li>"; }).join("") +
              "</ul>");
            d.insertBefore(wrap, acts);
          });
      };
      acts.appendChild(view);
      var del = el("button", "hcvre-btn gray", "DELETE");
      del.onclick = function (e) {
        e.stopPropagation();
        fetch("/api/vre/blueprint/" + bp.id, { method: "DELETE" }).then(load);
      };
      acts.appendChild(del);
    }
    d.appendChild(acts);
    return d;
  }

  var activeId = null;
  function load() {
    fetch("/api/vre/active").then(function (r) { return r.json(); })
      .then(function (a) {
        activeId = a.id;
        activeBox.innerHTML = a.id
          ? '<div class="hcvre-on"><span class="hcvre-dot"></span>ACTIVE STYLE: <b>' +
            esc(a.name) + '</b><button class="hcvre-btn gray" ' +
            'style="margin:0 0 0 auto" id="hcvre-off">OFF</button></div>'
          : "";
        var off = document.getElementById("hcvre-off");
        if (off) off.onclick = function () {
          fetch("/api/vre/activate", { method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: null }) }).then(load);
        };
      }).catch(function () {});
    fetch("/api/vre/blueprints").then(function (r) { return r.json(); })
      .then(function (bps) {
        list.innerHTML = "";
        if (!bps.length) {
          list.appendChild(el("div", "hcvre-empty",
            "No blueprints yet - analyze a viral video above. The style " +
            "you activate is applied automatically to your next job."));
          return;
        }
        bps.forEach(function (b) { list.appendChild(bpCard(b, false)); });
      }).catch(function () {});
  }

  var polling = null;
  function poll() {
    fetch("/api/vre/status").then(function (r) { return r.json(); })
      .then(function (s) {
        if (s.state === "running") {
          bar.style.display = "block";
          bar.firstChild.style.width = Math.round((s.frac || 0) * 100) + "%";
          msg.style.display = "block";
          msg.textContent = (s.log && s.log.length
            ? s.log[s.log.length - 1] : "working...");
          go.disabled = true;
        } else {
          bar.style.display = "none";
          go.disabled = false;
          if (polling) { clearInterval(polling); polling = null; }
          if (s.state === "error") {
            msg.style.display = "block";
            msg.textContent = "failed: " + (s.error || "unknown");
          } else if (s.state === "done") {
            msg.style.display = "none";
            load();
          }
        }
      }).catch(function () {});
  }
  go.onclick = function () {
    if (!urlIn.value.trim()) { return; }
    msg.style.display = "block";
    msg.textContent = "starting...";
    fetch("/api/vre/analyze", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: urlIn.value.trim(),
                             deep: deep.firstChild.checked }) })
      .then(function (r) { return r.json().then(function (d) {
        return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { msg.textContent = res.d.detail || "failed"; return; }
        if (!polling) polling = setInterval(poll, 1500);
        poll();
      }).catch(function () { msg.textContent = "network error"; });
  };

  load();
  setInterval(function () {
    if (!polling) return;
  }, 60000);
})();
