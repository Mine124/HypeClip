const $=s=>document.querySelector(s),$$=s=>document.querySelectorAll(s);
let jobId=null,timer=null,wizStep=1,rect=null,mediaSet=false,activeJob=false;

/* ---------- sliders ---------- */
const OUT={optDur:"#durOut",optPre:"#preOut",optSens:"#senOut"};
function paint(el){const mn=+el.min||0,mx=+el.max||100;
 el.style.setProperty("--fill",((el.value-mn)/(mx-mn)*100)+"%");
 const o=OUT[el.id];if(o)$(o).textContent=el.value;}
$$("input[type=range]").forEach(el=>{el.addEventListener("input",()=>paint(el));paint(el);});
$$("#segAspect button").forEach(b=>b.onclick=()=>{
 $$("#segAspect button").forEach(x=>x.classList.remove("active"));b.classList.add("active");});

function opts(){return{
 max_clips:+$("#optClips").value,clip_duration:+$("#optDur").value,
 pre_roll:+$("#optPre").value,hype_threshold:+$("#optSens").value,
 max_height:+$("#optHeight").value,fps:+($("#optFps")?.value||60),
 aspect:$("#segAspect button.active").dataset.a,
 caption_style:$("#optCapStyle").value,autocaptions:$("#optCaps").checked,
 sfx_enabled:$("#optSfx").checked,zoom_punch:$("#optZoom").checked,
 beat_sync:$("#optBeat").checked,fx_look:$("#optLook").value};}

function toast(msg,cls=""){const t=document.createElement("div");
 t.className="toast "+cls;t.textContent=msg;$("#toasts").append(t);
 setTimeout(()=>{t.style.opacity=0;setTimeout(()=>t.remove(),300)},3800);}

fetch("/api/meta").then(r=>r.json()).then(m=>{
 $("#engineDot").className="dot ok";$("#engineTxt").textContent="v"+m.version;})
.catch(()=>{$("#engineDot").className="dot bad";});
$("#folderBtn").onclick=()=>fetch("/api/meta").then(r=>r.json()).then(m=>
 fetch("/api/reveal",{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({path:m.out_dir})}));

/* ---------- wizard open/close (view-only toggling) ---------- */
function openWizard(){$("#wiz").classList.remove("hidden");}
function closeWizard(){$("#wiz").classList.add("hidden");}
$("#wizClose").onclick=closeWizard;

/* REOPEN BUTTON: lives in the header, works anytime, NEVER starts a job */
(function(){
 const b=document.createElement("button");
 b.className="ghost-btn";b.id="wizToggleBtn";
 b.textContent="🎛 Wizard";
 b.title="Show / hide the job wizard";
 b.onclick=()=>{
   const w=$("#wiz");
   w.classList.toggle("hidden");
   if(!w.classList.contains("hidden")&&typeof wizStep==="number")setStep(wizStep);
 };
 const hr=document.querySelector(".head-right");
 if(hr)hr.prepend(b);
})();

/* clicking outside the card also closes (reopen via 🎧 button) */
$("#wiz").addEventListener("mousedown",e=>{
 if(e.target.id==="wiz")closeWizard();});

function setStep(n){wizStep=n;
 $$(".wstep").forEach(s=>{const k=+s.dataset.w;
  s.classList.toggle("active",k===n);s.classList.toggle("done",k<n);});
 $$(".wiz-steps i").forEach((l,i)=>l.classList.toggle("fill",i<n-1));
 $$(".wpanel").forEach((p,i)=>p.classList.toggle("hidden",i!==n-1));}
/* server-driven navigation: FORWARD ONLY - never yanked backwards */
const STAGE_STEP={"awaiting_selection":1,"awaiting_command":3,
 "scan":2,"review":3,"clip":4,"done":4};
function syncStepFromServer(stage){
 const target=STAGE_STEP[stage];
 if(target&&target>wizStep)setStep(target);}

/* ---------- rectangle drawing ---------- */
let drawing=false,sx=0,sy=0;
function updateScanBtn(){
 const scanning=$("#btnScan").dataset.scanning==="1";
 $("#btnScan").disabled=scanning||(!$("#noChat").checked&&!rect);
 $("#btnScan").textContent=scanning?"scanning…":"Start scanning ✨";}
$("#btnDraw").onclick=()=>{const d=!$("#vidwrap").classList.contains("drawing");
 $("#vidwrap").classList.toggle("drawing",d);
 $("#drawShade").classList.toggle("hidden",!d);
 $("#drawHint").classList.toggle("hidden",!d);
 $("#btnDraw").textContent=d?"✓ Done drawing":"📐 Select chat area";};
$("#vidwrap").addEventListener("mousedown",e=>{
 if(!$("#vidwrap").classList.contains("drawing"))return;
 const r=$("#vidwrap").getBoundingClientRect();
 sx=e.clientX-r.left;sy=e.clientY-r.top;drawing=true;
 const b=$("#rectBox");b.classList.remove("hidden");
 b.style.left=sx+"px";b.style.top=sy+"px";b.style.width=b.style.height="0px";});
addEventListener("mousemove",e=>{
 if(!drawing)return;const r=$("#vidwrap").getBoundingClientRect();
 const x=Math.max(0,Math.min(e.clientX-r.left,r.width)),
       y=Math.max(0,Math.min(e.clientY-r.top,r.height));
 const b=$("#rectBox");
 b.style.left=Math.min(sx,x)+"px";b.style.top=Math.min(sy,y)+"px";
 b.style.width=Math.abs(x-sx)+"px";b.style.height=Math.abs(y-sy)+"px";});
addEventListener("mouseup",()=>{
 if(!drawing)return;drawing=false;
 const r=$("#vidwrap").getBoundingClientRect(),b=$("#rectBox");
 const bw=parseFloat(b.style.width),bh=parseFloat(b.style.height);
 if(bw<12||bh<12){b.classList.add("hidden");return;}
 rect={x:parseFloat(b.style.left)/r.width,y:parseFloat(b.style.top)/r.height,
       w:bw/r.width,h:bh/r.height};
 updateScanBtn();toast("chat area locked in","ok");});
$("#noChat").addEventListener("change",updateScanBtn);

$("#btnScan").onclick=async()=>{
 if($("#btnScan").disabled)return;
 const mode=$("#noChat").checked?"audio":"chat";
 if(mode==="chat"&&!rect)return toast("draw the rectangle first","err");
 $("#btnScan").dataset.scanning="1";updateScanBtn();
 await fetch(`/api/jobs/${jobId}/select`,{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({mode,rect})});setStep(2);};

$("#btnRescan").onclick=async()=>{
 await fetch(`/api/jobs/${jobId}/rescan`,{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({threshold:+$("#rescanSens").value})});setStep(2);};

$("#btnConfirm").onclick=async()=>{
 await fetch(`/api/jobs/${jobId}/confirm`,{method:"POST"});setStep(4);};

/* ---------- chart helper ---------- */
function line(cv,score,color){
 const ctx=cv.getContext("2d"),dpr=devicePixelRatio||1;
 cv.width=cv.clientWidth*dpr;cv.height=+cv.getAttribute("height")*dpr;
 ctx.clearRect(0,0,cv.width,cv.height);
 if(score.length<2)return;
 const mx=Math.max(...score,.001),W=cv.width,H=cv.height,p=8*dpr;
 ctx.beginPath();
 score.forEach((v,i)=>{const X=p+i/(score.length-1)*(W-2*p),
  Y=H-p-(v/mx)*(H-2*p);i?ctx.lineTo(X,Y):ctx.moveTo(X,Y);});
 ctx.strokeStyle=color;ctx.lineWidth=1.5*dpr;
 ctx.shadowColor="#7c5cff";ctx.shadowBlur=8*dpr;ctx.stroke();}

/* ---------- master poll ---------- */
timer=setInterval(async()=>{
 if(!jobId)return;
 let j;try{j=await(await fetch("/api/jobs/"+jobId)).json();}catch(e){return;}

 $("#statusWrap").classList.remove("hidden");
 $("#jobTitle").textContent=j.title||"";

 const st=j.stage;
 syncStepFromServer(st);

 if(st==="awaiting_selection"){
   $("#prepFill").style.width="100%";
   $("#prepTxt").textContent=j.duration?
     `video ready (${Math.round(j.duration/60)} min) — draw over the chat!`
     :"fetching video…";}

 if(st==="scan"){
   $("#btnScan").dataset.scanning="1";
   $("#scanPct").textContent=Math.round((j.scan_frac||0)*100)+"%";
   line($("#scanChart"),(j.series&&j.series.score)||[],"#a78bfa");}
 else if($("#btnScan").dataset.scanning==="1"&&st!=="scan"){
   $("#btnScan").dataset.scanning="0";}
 updateScanBtn();

 if(st==="review"&&wizStep===2){setStep(3);}
 if(st==="review")renderPeaks(j);

 if(st==="clip"||st==="done"||st==="record"){
   $("#renFill").style.width=Math.round((j.progress||0)*100)+"%";
   $("#renTxt").textContent=`${(j.clips||[]).length} clip(s) ready`;}
 $("#pfill").style.width=Math.round((j.progress||0)*100)+"%";
 $("#pct").textContent=Math.round((j.progress||0)*100)+"%";
 line($("#chart"),(j.series&&j.series.score)||[],"#a78bfa");

 if(!mediaSet&&j.media_url){mediaSet=true;$("#wizVideo").src=j.media_url;}
 const lg=$("#log"),stick=lg.scrollTop+lg.clientHeight>=lg.scrollHeight-40;
 lg.textContent=(j.logs||[]).join("\n");if(stick)lg.scrollTop=lg.scrollHeight;
 (j.clips||[]).forEach(c=>{
   addClip(c,"#clipsGrid");addClip(c,"#wizClips");});
 if(["done","error","stopped"].includes(j.state)){
   activeJob=false;
   if(j.state==="done")toast("all clips ready! 🎉","ok");
   if(j.state==="error"){toast(j.error,"err");$("#errBox").textContent=j.error;}}
},1100);

function renderPeaks(j){
 $("#peaks").innerHTML=(j.moments||[]).map(m=>{
  const fmt=s=>`${String(Math.floor(s/60)).padStart(2,"0")}:${String(Math.round(s%60)).padStart(2,"0")}`;
  return`<div class="peak"><span class="t">${fmt(m.start)} → ${fmt(m.end)}</span>
   <span class="flex1"></span><b>🔥 ${m.score}</b></div>`;}).join("")
  ||'<p class="hint">nothing above threshold — lower sensitivity and re-scan</p>';
 $("#rescanSens").value=+$("#optSens").value;paint($("#rescanSens"));}

function addClip(c,sel){
 const grid=$(sel);if(!grid||grid.querySelector(`[data-f="${CSS.escape(c.file)}"]`))return;
 const el=document.createElement("div");el.className="clip";el.dataset.f=c.file;
 el.innerHTML=`<video src="${c.url}" preload="metadata" muted loop playsinline></video>
  <div class="meta"><span class="badge">${c.score!==""?("🔥 "+c.score):c.platform||"clip"}</span>
  <span>${c.duration}s</span>
  <div class="btns"><a class="icon-btn" href="${c.url}" download="${c.file}">save</a></div></div>`;
 const v=el.querySelector("video");
 el.onmouseenter=()=>v.play().catch(()=>{});
 el.onmouseleave=()=>{v.pause();v.currentTime=0;};
 grid.prepend(el);}

/* ---------- start job ---------- */
async function start(){
 if(activeJob){toast("a job is already running — wait or Stop it first","err");return;}
 const url=$("#urlInput").value.trim();
 if(!url)return toast("paste a link first","err");
 const res=await fetch("/api/jobs",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({url,options:opts()})});
 if(!res.ok)return toast("failed to start","err");
 jobId=(await res.json()).job_id;mediaSet=false;activeJob=true;
 rect=null;$("#rectBox").classList.add("hidden");
 $("#btnScan").dataset.scanning="0";
 $("#clipsGrid").innerHTML="";
 setStep(1);openWizard();}
$("#goBtn").onclick=start;
$("#urlInput").addEventListener("keydown",e=>e.key==="Enter"&&start());
addEventListener("keydown",e=>{if(e.ctrlKey&&e.key==="Enter")start();});

/* ======== Brand Kit + scan-fps ======== */
(function(){
 const css=document.createElement("style");css.textContent=`
 .bk-btn{position:fixed;left:20px;bottom:20px;z-index:45;}
 .bk-panel{position:fixed;left:20px;bottom:72px;z-index:46;width:330px;
  background:#0d1019;border:1px solid rgba(255,255,255,.1);border-radius:16px;
  padding:16px;display:none;box-shadow:0 20px 50px -12px #000d}
 .bk-panel.open{display:block}
 .bk-row{display:flex;gap:8px;margin-top:10px}
 .bk-panel input,.bk-panel select{background:#0b0d15;color:#fff;border:1px solid
  rgba(255,255,255,.13);border-radius:9px;padding:9px 11px;outline:none;width:100%;font-size:13px}
 .bk-chip{display:inline-flex;align-items:center;gap:6px;background:#141827;
  border-radius:99px;padding:5px 6px 5px 12px;font-size:12px;margin:6px 6px 0 0}
 .bk-chip.active{outline:2px solid #7c5cff}
 .bk-chip button{background:none;border:none;color:#fb7185;cursor:pointer;font-size:13px}
 .bk-chip .act{color:#67e8f9;cursor:pointer;background:none;border:none;font-size:11px}
 .bk-preview{width:100%;margin-top:10px;border-radius:10px;background:#151a28}`;
 document.head.append(css);

 const btn=document.createElement("button");btn.className="mini-btn bk-btn";
 btn.textContent="🎨 Brand kit";document.body.append(btn);
 const p=document.createElement("div");p.className="bk-panel";
 p.innerHTML=`<b style="font-size:13px">Cartoon Subscribe Buttons</b>
  <div class="bk-row"><input id="bkName" placeholder="streamer name e.g. IShowSpeed"/>
  <select id="bkStyle"><option>bubble</option><option>burst</option>
  <option>wobble</option></select></div>
  <div class="bk-row"><button class="mini-btn accent" id="bkAdd" style="flex:1">
   ✨ Generate button</button></div>
  <img id="bkPrev" class="bk-preview" alt=""/>
  <div id="bkList" style="margin-top:8px"></div>
  <div class="bk-row"><label style="font-size:12px;color:#8b93a7">
   <input type="checkbox" id="bkOn" checked style="width:auto"/> Stamp onto clips</label>
  <select id="bkPos" style="flex:1"><option value="br">bottom right</option>
   <option value="bl">bottom left</option><option value="tr">top right</option>
   <option value="tl">top left</option></select></div>
  <div class="bk-row"><label style="font-size:12px;color:#8b93a7">Appears</label>
   <select id="bkWhen" style="flex:1"><option value="start">at clip start</option>
   <option value="end">near clip end</option></select>
   <select id="bkDur"><option>3</option><option selected>4</option>
   <option>6</option><option>8</option></select></div>`;
 document.body.append(p);
 btn.onclick=()=>p.classList.toggle("open");

 async function refreshBk(){
  const st=await(await fetch("/api/streamers")).json();
  $("#bkList").innerHTML=(st.streamers||[]).map(s=>
   `<span class="bk-chip ${s.name===st.active?"active":""}">
    <span class="act" data-a="${s.name}">${s.name===st.active?"★":"☆"}</span>
    ${s.name}<button data-d="${s.name}">✕</button></span>`).join("");
  p.querySelectorAll("[data-d]").forEach(b=>b.onclick=async()=>{
   await fetch("/api/streamers?name="+encodeURIComponent(b.dataset.d),
    {method:"DELETE"});refreshBk();});
  p.querySelectorAll("[data-a]").forEach(b=>b.onclick=async()=>{
   await fetch("/api/streamers/activate",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({name:b.dataset.a})});refreshBk();});
 }
 $("#bkAdd").onclick=async()=>{
  const n=$("#bkName").value.trim();
  if(!n)return toast("type a streamer name","err");
  await(await fetch("/api/streamers",{method:"POST",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify({name:n,style:$("#bkStyle").value})})).json();
  $("#bkName").value="";
  $("#bkPrev").src="/api/streamers/preview.png?name="+encodeURIComponent(n)
   +"&style="+$("#bkStyle").value+"&t="+Date.now();
  toast("cartoon button ready 🎨","ok");refreshBk();};
 $("#bkName").addEventListener("input",()=>{
  const n=$("#bkName").value.trim();if(!n)return;
  $("#bkPrev").src="/api/streamers/preview.png?name="+encodeURIComponent(n)
   +"&style="+$("#bkStyle").value+"&t="+Date.now();});
 refreshBk();

 try{
  const grid=document.querySelector(".hero details .grid");
  if(grid&&!document.getElementById("optScanFps")){
   const lab=document.createElement("label");
   lab.innerHTML='<span>Scan precision <b class="val">'+
    '<output id="sfpsOut">6</output> fps</b></span>'+
    '<input id="optScanFps" type="range" min="2" max="30" value="6"/>';
   grid.append(lab);
   const el=lab.querySelector("input");
   const setF=()=>{$("#sfpsOut").textContent=el.value;
    el.style.setProperty("--fill",((el.value-2)/28*100)+"%");};
   el.addEventListener("input",setF);setF();
  }}catch(e){}
})();

/* wrap start() to attach branding + scan fps, keeping the guard */
(function(){
 const _orig=start;
 start=async function(){
  if(activeJob){toast("a job is already running — wait or Stop it first","err");return;}
  const url=$("#urlInput").value.trim();
  if(!url)return toast("paste a link first","err");
  const base=opts();
  try{
   if($("#bkOn")&&$("#bkOn").checked){
    const st=await(await fetch("/api/streamers")).json();
    if(st.active){base.sub_name=st.active;base.sub_pos=$("#bkPos").value;
     base.sub_when=$("#bkWhen").value;base.sub_dur=+$("#bkDur").value;}}
  }catch(e){}
  if($("#optScanFps"))base.scan_fps=+$("#optScanFps").value;
  const res=await fetch("/api/jobs",{method:"POST",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify({url,options:base})});
  if(!res.ok)return toast("failed to start","err");
  jobId=(await res.json()).job_id;mediaSet=false;activeJob=true;
  rect=null;$("#rectBox").classList.add("hidden");
  $("#btnScan").dataset.scanning="0";
  $("#clipsGrid").innerHTML="";
  setStep(1);openWizard();};
 $("#goBtn").onclick=start;
})();

/* ======== Export menu: multi-format downloads ======== */
(function(){
 const FORMATS=[
  ["tiktok","TikTok · 9:16 · 1080p60"],
  ["shorts","Shorts · 9:16 · 1080p60"],
  ["reels","Reels · 9:16 · 1080p60"],
  ["youtube","YouTube · 16:9 · 1080p60"],
  ["square","Square 1:1 · 1080p60"],
  ["hd720","MP4 · 720p60"],
  ["sd480","MP4 · 480p30 (small file)"],
  ["webm_hd","WebM · 1080p60"]];
 const st=document.createElement("style");st.textContent=`
 .exp-menu{position:fixed;z-index:70;background:#0d1019;
  border:1px solid rgba(255,255,255,.12);border-radius:12px;padding:8px;
  display:flex;flex-direction:column;gap:4px;width:250px;
  box-shadow:0 20px 50px -12px #000d}
 .exp-menu button{background:#141827;border:none;color:#dbe2f2;text-align:left;
  padding:9px 11px;border-radius:8px;font-size:12.5px;cursor:pointer}
 .exp-menu button:hover{background:#7c5cff33;color:#fff}
 .exp-menu button:disabled{opacity:.55;cursor:wait}`;
 document.head.append(st);

 const menu=document.createElement("div");
 menu.className="exp-menu hidden";
 menu.innerHTML=FORMATS.map(([id,l])=>`<button data-plat="${id}">${l}</button>`).join("");
 document.body.append(menu);

 let curFile=null;
 document.addEventListener("click",e=>{
  const btn=e.target.closest("[data-export]");
  if(btn){
   if(btn.tagName==="A")e.preventDefault();
   curFile=btn.getAttribute("data-export");
   const r=btn.getBoundingClientRect();
   menu.style.left=Math.max(8,Math.min(r.left,innerWidth-266))+"px";
   menu.style.top=Math.max(8,Math.min(r.bottom+6,innerHeight-380))+"px";
   menu.classList.toggle("hidden");return;}
  if(!e.target.closest(".exp-menu"))menu.classList.add("hidden");
 });

 async function runExport(plat,fileBtn){
  fileBtn.disabled=true;const orig=fileBtn.textContent;
  fileBtn.textContent="rendering…";
  try{
   const res=await(await fetch("/api/export",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({file:curFile,platform:plat})})).json();
   const tick=setInterval(async()=>{
    const s=await(await fetch("/api/export/"+res.export_id)).json();
    if(s.state==="done"){clearInterval(tick);
     toast(plat.toUpperCase()+" exported 📦","ok");
     addClip(s.result,"#clipsGrid");
     fileBtn.textContent=orig;fileBtn.disabled=false;
     menu.classList.add("hidden");}
    else if(s.state==="error"){clearInterval(tick);
     toast(s.error,"err");
     fileBtn.textContent=orig;fileBtn.disabled=false;}},1200);
  }catch(err){toast(String(err),"err");
   fileBtn.textContent=orig;fileBtn.disabled=false;}
 }
 menu.addEventListener("click",e=>{
  const b=e.target.closest("button[data-plat]");
  if(b&&curFile)runExport(b.dataset.plat,b);
 });

 function watchGrid(gridId){
  const grid=document.getElementById(gridId);if(!grid)return;
  const decorate=()=>grid.querySelectorAll(".clip:not([data-exp])").forEach(card=>{
   card.dataset.exp="1";
   const btns=card.querySelector(".btns"),file=card.dataset.f;
   if(!btns||!file)return;
   const ex=document.createElement("button");
   ex.className="icon-btn";ex.textContent="export ⬇";
   ex.setAttribute("data-export",file);
   btns.prepend(ex);});
  decorate();
  new MutationObserver(decorate).observe(grid,{childList:true});
 }
 watchGrid("clipsGrid");watchGrid("wizClips");
})();

/* ======== Wizard Back / Next navigation (view-only, progress-gated) ======== */
(function(){
 const st=document.createElement("style");st.textContent=`
 .wiz-nav{display:flex;align-items:center;gap:10px;margin-top:18px;
  border-top:1px dashed var(--line);padding-top:14px}
 #wizPos{font-size:12px}`;
 document.head.append(st);

 const card=document.querySelector(".wiz-card");
 if(!card)return;
 const bar=document.createElement("div");bar.className="wiz-nav";
 bar.innerHTML=`<button id="wizBack" class="mini-btn">&#9664; Back</button>
  <span id="wizPos" class="dim"></span><span class="flex1"></span>
  <button id="wizFwd" class="mini-btn accent">Next &#9654;</button>`;
 card.append(bar);

 let maxStep=1,prevJob=null;

 const _setStep=setStep;
 setStep=function(n){
  n=Math.max(1,Math.min(4,n|0));
  if(n>maxStep)maxStep=n;
  _setStep(n);
  const pos=$("#wizPos"),f=$("#wizFwd"),b=$("#wizBack");
  if(pos)pos.textContent=`step ${wizStep} of 4`;
  if(f)f.disabled=wizStep>=maxStep;
  if(b)b.disabled=wizStep<=1;
 };

 async function serverMax(){
  if(!jobId)return 1;
  try{
   const j=await(await fetch("/api/jobs/"+jobId)).json();
   const s=j.stage||"";
   if(j.state==="error")return maxStep;
   if(s==="clip"||s==="done"||(j.clips&&j.clips.length))return 4;
   if(s==="review"||s==="awaiting_command")return 3;
   if(s==="scan")return 2;
   return 1;
  }catch(e){return 1;}
 }

 $("#wizBack").onclick=()=>{
  if(wizStep>1){setStep(wizStep-1);}
 };
 $("#wizFwd").onclick=async()=>{
  const cap=await serverMax();
  if(wizStep>=cap){
   const why={1:"the video is still downloading",
              2:"no scan has finished yet",
              3:"review your peaks and click Render clips first"}[cap]
             ||"finish this step first";
   return toast("can't skip ahead — "+why,"err");}
  setStep(Math.min(4,wizStep+1));
 };

 addEventListener("keydown",e=>{
  if($("#wiz").classList.contains("hidden"))return;
  const t=document.activeElement&&document.activeElement.tagName;
  if(t==="INPUT"||t==="TEXTAREA"||t==="SELECT")return;
  if(e.key==="ArrowLeft")$("#wizBack").click();
  if(e.key==="ArrowRight")$("#wizFwd").click();
 });

 setInterval(()=>{
  if(jobId!==prevJob){prevJob=jobId;if(jobId){maxStep=1;setStep(1);}}
 },800);

 /* reopening the popup restores the correct step */
 const _open=openWizard;
 openWizard=function(){_open();if(typeof wizStep==="number")setStep(wizStep);};
})();
