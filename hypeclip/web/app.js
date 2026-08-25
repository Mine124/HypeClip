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
 beat_sync:$("#optBeat").checked,flash_intro:$("#optFlash").checked,
 bloom:$("#optBloom").checked,grain:$("#optGrain").checked,
 vignette:$("#optVig").checked,fx_look:$("#optLook").value,
 auto_render:$("#optAuto")?$("#optAuto").checked:true,
 enhance:false,enhance_mode:"light"};}

function toast(msg,cls=""){const t=document.createElement("div");
 t.className="toast "+cls;t.textContent=msg;$("#toasts").append(t);
 setTimeout(()=>{t.style.opacity=0;setTimeout(()=>t.remove(),300)},3800);}

fetch("/api/meta").then(r=>r.json()).then(m=>{
 $("#engineDot").className="dot ok";$("#engineTxt").textContent="v"+m.version;})
.catch(()=>{$("#engineDot").className="dot bad";});
$("#folderBtn").onclick=()=>fetch("/api/meta").then(r=>r.json()).then(m=>
 fetch("/api/reveal",{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({path:m.out_dir})}));

/* ---------- wizard show/hide (view-only) ---------- */
function openWizard(){$("#wiz").classList.remove("hidden");}
function closeWizard(){$("#wiz").classList.add("hidden");}
$("#wizClose").onclick=closeWizard;
$("#wiz").addEventListener("mousedown",e=>{
 if(e.target.id==="wiz")closeWizard();});

/* REOPEN BUTTON - always available, never starts a job */
(function(){
 const b=document.createElement("button");
 b.className="ghost-btn";b.id="wizToggleBtn";b.textContent="🎛 Wizard";
 b.title="Show / hide the job wizard";
 b.onclick=()=>{const w=$("#wiz");w.classList.toggle("hidden");
  if(!w.classList.contains("hidden")&&typeof wizStep==="number")setStep(wizStep);};
 const hr=document.querySelector(".head-right");
 if(hr)hr.prepend(b);
})();

function setStep(n){wizStep=n;
 $$(".wstep").forEach(s=>{const k=+s.dataset.w;
  s.classList.toggle("active",k===n);s.classList.toggle("done",k<n);});
 $$(".wiz-steps i").forEach((l,i)=>l.classList.toggle("fill",i<n-1));
 $$(".wpanel").forEach((p,i)=>p.classList.toggle("hidden",i!==n-1));}
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

 if(st==="clip"&&wizStep<4)setStep(4);
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

/* ---------- shared option gathering ---------- */
function attachBranding(base){
 try{
  const on=document.getElementById("bkOn");
  if(on&&on.checked&&document.getElementById("bkPos")){
   return fetch("/api/streamers").then(r=>r.json()).then(st=>{
    if(st.active){base.sub_name=st.active;base.sub_pos=$("#bkPos").value;
     base.sub_when=$("#bkWhen").value;base.sub_dur=+$("#bkDur").value;}
    return base;});}
 }catch(e){}
 return Promise.resolve(base);}
function beginJob(id){
 jobId=id;mediaSet=false;activeJob=true;
 rect=null;$("#rectBox").classList.add("hidden");
 $("#btnScan").dataset.scanning="0";
 $("#clipsGrid").innerHTML="";
 setStep(1);openWizard();}

/* ---------- start from LINK ---------- */
async function start(){
 if(activeJob){toast("a job is already running — wait or Stop it first","err");return;}
 const url=$("#urlInput").value.trim();
 if(!url)return toast("paste a link first","err");
 const base=opts();
 try{
  const on=document.getElementById("bkOn");
  if(on&&on.checked&&document.getElementById("bkPos")){
   const st=await(await fetch("/api/streamers")).json();
   if(st.active){base.sub_name=st.active;base.sub_pos=$("#bkPos").value;
    base.sub_when=$("#bkWhen").value;base.sub_dur=+$("#bkDur").value;}}
 }catch(e){}
 const res=await fetch("/api/jobs",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({url,options:base})});
 if(!res.ok)return toast("failed to start","err");
 beginJob((await res.json()).job_id);}
$("#goBtn").onclick=start;
$("#urlInput").addEventListener("keydown",e=>e.key==="Enter"&&start());
addEventListener("keydown",e=>{if(e.ctrlKey&&e.key==="Enter")start();});

/* ---------- start from FILE UPLOAD ---------- */
(function(){
 const dz=$("#dropZone"),fi=$("#fileInput");
 dz.onclick=()=>fi.click();
 dz.addEventListener("dragover",e=>{e.preventDefault();dz.classList.add("drag");});
 dz.addEventListener("dragleave",()=>dz.classList.remove("drag"));
 dz.addEventListener("drop",e=>{e.preventDefault();dz.classList.remove("drag");
  if(e.dataTransfer.files.length)handleFile(e.dataTransfer.files[0]);});
 fi.addEventListener("change",()=>{if(fi.files.length)handleFile(fi.files[0]);});

 async function handleFile(f){
  if(activeJob){toast("a job is already running — wait or Stop it first","err");return;}
  toast("uploading "+f.name+" …");
  const fd=new FormData();
  fd.append("options",JSON.stringify(opts()));
  fd.append("file",f);
  try{
   const res=await fetch("/api/jobs/upload",{method:"POST",body:fd});
   if(!res.ok)return toast((await res.json()).detail||"upload failed","err");
   beginJob((await res.json()).job_id);
   toast("upload complete — wizard opened","ok");
  }catch(err){toast("upload failed: "+err,"err");}
  finally{fi.value="";}
 }
})();

/* ======== ✨ AI Enhance v2 (light / heavy) ======== */
(function(){
 /* remove the old single-tick control if it exists */
 const old=document.getElementById("optEnh");
 if(old&&old.closest("label"))old.closest("label").remove();

 const grid=document.querySelector(".hero details .grid");
 if(grid&&!document.getElementById("optEnh")){
  const lab=document.createElement("label");
  lab.className="sw";
  lab.innerHTML='<input type="checkbox" id="optEnh"/><i></i>✨ AI Enhance';
  grid.append(lab);
  const modes=document.createElement("label");
  modes.id="enhModes";
  modes.style.display="none";
  modes.innerHTML='<span style="font-size:11px">Mode</span>'+
   '<select id="optEnhMode">'+
   '<option value="light">Light — instant · subtle crisp</option>'+
   '<option value="heavy">Heavy — neural upscale · ultra-crisp (very slow)</option>'+
   '</select>';
  grid.append(modes);
  lab.querySelector("input").addEventListener("change",e=>{
   modes.style.display=e.target.checked?"flex":"none";});
 }

 /* patch opts() so enhance settings ride along on every job submission */
 const _origOpts=opts;
 opts=function(){
  const base=_origOpts();
  const el=document.getElementById("optEnh");
  const md=document.getElementById("optEnhMode");
  base.enhance=el?el.checked:false;
  base.enhance_mode=md?md.value:"light";
  return base;
 };
})();

/* ======== Scan precision slider ======== */
(function(){
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

/* ======== Brand Kit ======== */
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
})();

/* ======== Export menu ======== */
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

/* ======== Back / Next navigation (view-only, gated) ======== */
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
  if(wizStep>1)setStep(wizStep-1);};
 $("#wizFwd").onclick=async()=>{
  const cap=await serverMax();
  if(wizStep>=cap){
   const why={1:"the video is still loading",
              2:"no scan has finished yet",
              3:"click Render clips first"}[cap]
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

 const _open=openWizard;
 openWizard=function(){_open();if(typeof wizStep==="number")setStep(wizStep);};
})();
/* ======== ✨ Aura polish: ripples ======== */
(function(){
 if(matchMedia("(prefers-reduced-motion: reduce)").matches)return;
 const st=document.createElement("style");st.textContent=`
 .ripple{position:absolute;border-radius:50%;pointer-events:none;
  background:radial-gradient(circle,#ffffff55,transparent 65%);
  transform:scale(0);animation:rip .55s var(--e-out,cubic-bezier(.22,1,.36,1)) forwards}
 @keyframes rip{to{transform:scale(3.2);opacity:0}}`;
 document.head.append(st);
 document.addEventListener("pointerdown",e=>{
  const b=e.target.closest(".cta,.mini-btn,.ghost-btn,.exp-chip");
  if(!b||getComputedStyle(b).position==="")b.style.position="relative";
  b.style.overflow="hidden";b.style.position=b.style.position||"relative";
  const r=b.getBoundingClientRect(),d=Math.max(r.width,r.height);
  const s=document.createElement("span");s.className="ripple";
  s.style.width=s.style.height=d+"px";
  s.style.left=(e.clientX-r.left-d/2)+"px";s.style.top=(e.clientY-r.top-d/2)+"px";
  b.append(s);setTimeout(()=>s.remove(),600);
 });
})();
/* ======== 🧠 Intelligence Pack: rich cards + batch + assistant + templates ======== */
(function(){
 /* ---- richer clip cards ---- */
 const CAT_EMOJI={funny:"😂",clutch:"🎯",win:"🏆",fail:"💀",rage:"😡",
  reaction:"😲",highlight:"⭐"};
 const _add=addClip;
 addClip=function(c,sel){
  const grid=$(sel);if(!grid||grid.querySelector(`[data-f="${CSS.escape(c.file)}"]`))return;
  const el=document.createElement("div");el.className="clip";el.dataset.f=c.file;
  const cat=c.category||"highlight";
  el.innerHTML=`<video src="${c.url}" ${c.thumb?`poster="${c.thumb}"`:""}
    preload="metadata" muted loop playsinline></video>
   <div class="meta"><span class="badge">${c.viral!=null&&c.viral!==""?
    `V${c.viral}`:`🔥 ${c.score}`}</span>
   <span class="badge" style="background:#7c5cff22;color:#c4b5fd">
    ${CAT_EMOJI[cat]||"⭐"} ${cat}</span>
   <span>${c.duration}s</span>
   <div class="btns"><button class="icon-btn" data-meta="${c.file}"
    title="copy title+hashtags">📋</button>
   <a class="icon-btn" href="${c.url}" download="${c.file}">save</a></div></div>`;
  if(c.thumbs&&c.thumbs.length>1){
   const th=document.createElement("div");
   th.style.cssText="display:flex;gap:6px;padding:6px 12px";
   c.thumbs.forEach(u=>{const im=document.createElement("img");
    im.src=u;im.style.cssText="width:31%;border-radius:6px;cursor:pointer";
    im.onclick=()=>open(u,"_blank");th.append(im);});
   el.querySelector(".meta").before(th);}
  const v=el.querySelector("video");
  el.onmouseenter=()=>v.play().catch(()=>{});
  el.onmouseleave=()=>{v.pause();v.currentTime=0;};
  el.querySelector("[data-meta]").onclick=async()=>{
   const m=c.meta||{};
   const txt=[m.title,m.desc,m.hashtags].filter(Boolean).join("\n\n");
   await navigator.clipboard.writeText(txt);
   toast(`metadata copied (SEO ${m.seo||""})`,"ok");};
  grid.prepend(el);};

 /* ---- batch queue: multiline links ---- */
 const _start=start;
 let QUEUE=[],pumping=false;
 const waitDone=()=>new Promise(res=>{const t=setInterval(async()=>{
  if(!jobId){clearInterval(t);res();return;}
  try{const j=await(await fetch("/api/jobs/"+jobId)).json();
   if(["done","error","stopped"].includes(j.state)){clearInterval(t);res();}}
  catch(e){}},1500);});
 async function pump(){if(pumping)return;pumping=true;
  while(QUEUE.length){const u=QUEUE.shift();
   toast(`batch: starting ${u.slice(0,48)}…`);
   $("#urlInput").value=u;await _start();await waitDone();}
  pumping=false;toast("batch complete 🎉","ok");}
 start=async function(){
  const raw=$("#urlInput").value.trim();
  const links=raw.split(/\s+/).filter(x=>/^https?:\/\//i.test(x));
  if(links.length>1){QUEUE.push(...links);
   toast(`queued ${links.length} links — processing one-by-one`,"ok");
   $("#urlInput").value="";
   if(!activeJob)pump();return;}
  await _start();if(QUEUE.length&&!pumping)pump();};

 /* ---- 🪄 AI assistant ---- */
 const st=document.createElement("style");st.textContent=`
 .askrow{display:flex;gap:8px;margin-top:10px}
 .askrow input{flex:1;background:#0a0c13;border:1px solid rgba(255,255,255,.13);
  border-radius:10px;padding:11px 14px;color:#fff;outline:none;font-size:13.5px}
 .askrow input:focus{border-color:#7c5cff}`;
 document.head.append(st);
 const row=document.createElement("div");row.className="askrow";
 row.innerHTML=`<input id="aiAsk"
  placeholder='🪄 Ask: "make it cinematic, shorter, more clips, vertical…"'/>`;
 $(".srcrow").after(row);
 const APPLY=[
  [/cinematic/,o=>{o.fx_look="cinematic";o.bloom=true;o.grain=true;o.vignette=true;
    return"cinematic grade+bloom+grain";}],
  [/gaming/,o=>{o.fx_look="capcut";o.zoom_punch=true;o.beat_sync=true;
    o.shake=.5;o.sfx_volume_db=8;return"gaming punch style";}],
  [/funny|meme/,o=>{o.flash_intro=true;o.zoom_punch=true;
    o.caption_style="karaoke";return"funny style (flash+karaoke)";}],
  [/minimal|clean|no filter/,o=>{o.fx_look="none";o.bloom=false;o.grain=false;
    o.vignette=false;o.zoom_punch=false;o.beat_sync=false;
    o.flash_intro=false;return"clean minimal look";}],
  [/vertical|tiktok|shorts|9:16/,o=>{o.aspect="9:16";return"vertical 9:16";}],
  [/horizontal|youtube|16:9|landscape/,o=>{o.aspect="16:9";return"wide 16:9";}],
  [/square/,o=>{o.aspect="1:1";return"square 1:1";}],
  [/shorter/,o=>{o.clip_duration=Math.max(15,o.clip_duration*.7);
    return"shorter clips";}],
  [/longer/,o=>{o.clip_duration=Math.min(180,o.clip_duration*1.3);
    return"longer clips";}],
  [/more clips/,o=>{o.max_clips=Math.min(20,(+$("#optClips").value||5)+2);
    return"more clips";}],
  [/fewer|less clips/,o=>{o.max_clips=Math.max(1,(+$("#optClips").value||5)-2);
    return"fewer clips";}],
  [/no caption|captions off/,o=>{o.autocaptions=false;return"captions off";}],
  [/caption/,o=>{o.autocaptions=true;return"captions on";}],
  [/no sfx|sfx off/,o=>{o.sfx_enabled=false;return"SFX off";}],
  [/sfx|sound effect/,o=>{o.sfx_enabled=true;return"SFX on";}],
  [/heavy|ultra crisp|max quality/,o=>{o.enhance=true;o.enhance_mode="heavy";
    return"Heavy neural enhance (slow!)";}],
  [/crisp|enhance|sharp/,o=>{o.enhance=true;o.enhance_mode="light";
    return"Light enhance";}],
  [/fast render|quick render/,o=>{o.max_height=720;o.fps=30;o.bloom=false;
    return"fast-render mode 720p30";}],
  [/1080|hd/,o=>{o.max_height=1080;return"1080p";}],
  [/autopilot off|manual/,o=>{o.auto_render=false;
    return"manual review mode";}],
  [/autopilot|auto pilot/,o=>{o.auto_render=true;return"autopilot on";}],
 ];
 function setOpt(key,val){
  const map={aspect:null,fx_look:"#optLook",caption_style:"#optCapStyle",
   max_height:"#optHeight",fps:"#optFps",max_clips:"#optClips",
   clip_duration:"#optDur",pre_roll:"#optPre",hype_threshold:"#optSens"};
  const id=map[key];
  if(id&&$(id)){$(id).value=val;if($(id).type==="range")paint($(id));return;}
  if(key==="aspect"){setA(val);return;}
  const cb={"autocaptions":"#optCaps","sfx_enabled":"#optSfx",
   "zoom_punch":"#optZoom","beat_sync":"#optBeat","flash_intro":"#optFlash",
   "bloom":"#optBloom","grain":"#optGrain","vignette":"#optVig",
   "auto_render":"#optAuto"}[key];
  if(cb&&$(cb)){ $(cb).checked=!!val; $(cb).dispatchEvent(new Event("change"));}
 }
 function setA(a){$$("#segAspect button").forEach(x=>
  x.classList.toggle("active",x.dataset.a===a));}
 $("#aiAsk").addEventListener("keydown",async e=>{
  if(e.key!=="Enter")return;
  const q=e.target.value.trim().toLowerCase();if(!q)return;
  const o=opts();const done=[];
  for(const[rx,fn]of APPLY){if(rx.test(q)){
   const msg=fn(o);if(msg)done.push(msg);markCustom&&markCustom();}}
  if(/\b(\d{2,3})\s*(s|sec|second)/.test(q)){
   const m=q.match(/\b(\d{2,3})\s*(s|sec)/);o.clip_duration=+m[1];
   done.push(o.clip_duration+"s clips");}
  for(const[k,v]of Object.entries(o))setOpt(k,v);
  e.target.value="";
  toast(done.length?"🪄 "+done.join(" · "):
   "try: cinematic · gaming · funny · minimal · vertical · shorter · "+
   "more clips · captions off · heavy crisp · autopilot off · 60s",
   done.length?"ok":"err");});

 /* ---- 🧩 Templates ---- */
 const tplRow=document.createElement("div");
 tplRow.style.cssText="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap";
 tplRow.innerHTML=`<select id="tplSel" style="max-width:170px">
  <option value="">templates…</option></select>
  <button class="mini-btn" id="tplSave">💾 Save</button>
  <button class="mini-btn" id="tplLoad">📂 Load</button>
  <button class="mini-btn danger" id="tplDel">🗑</button>`;
 document.querySelector(".hero details.panel").prepend(tplRow);
 const TKEY="hc_templates";
 const tpls=()=>JSON.parse(localStorage.getItem(TKEY)||"{}");
 const refreshTpl=()=>{
  const s=tpls();$("#tplSel").innerHTML='<option value="">templates…</option>'+
   Object.keys(s).map(k=>`<option>${k}</option>`).join("");};
 refreshTpl();
 $("#tplSave").onclick=()=>{
  const name=prompt("Template name:","My Style");if(!name)return;
  const s=tpls();s[name]=opts();localStorage.setItem(TKEY,JSON.stringify(s));
  refreshTpl();toast(`template "${name}" saved 🧩`,"ok");};
 $("#tplLoad").onclick=()=>{
  const n=$("#tplSel").value;if(!n)return toast("pick a template first","err");
  const s=tpls();applyOpts(s[n]||{});
  toast(`template "${n}" loaded 🧩`,"ok");};
 $("#tplDel").onclick=()=>{
  const n=$("#tplSel").value;if(!n)return;
  const s=tpls();delete s[n];localStorage.setItem(TKEY,JSON.stringify(s));
  refreshTpl();toast("deleted");};
 function applyOpts(o){
  for(const[k,v]of Object.entries(o)){
   if(k==="aspect"){setA(v);continue;}
   const id={"fx_look":"#optLook","caption_style":"#optCapStyle",
    "max_height":"#optHeight","fps":"#optFps","max_clips":"#optClips",
    "clip_duration":"#optDur","pre_roll":"#optPre",
    "hype_threshold":"#optSens"}[k];
   const cb={"autocaptions":"#optCaps","sfx_enabled":"#optSfx",
    "zoom_punch":"#optZoom","beat_sync":"#optBeat",
    "flash_intro":"#optFlash","bloom":"#optBloom","grain":"#optGrain",
    "vignette":"#optVig","auto_render":"#optAuto"}[k];
   if(id&&$(id)){$(id).value=v;if($(id).type==="range")paint($(id));}
   else if(cb&&$(cb)){$(cb).checked=!!v;$(cb).dispatchEvent(new Event("change"));}}
  const em=document.getElementById("optEnhMode");
  if(em&&o.enhance_mode)em.value=o.enhance_mode;}
})();
/* ======== 🦅 Eagle-Eye click-to-track ======== */
(function(){
 const b=document.createElement("button");b.className="mini-btn";
 b.id="btnTrack";b.textContent="🦅 Track object";b.disabled=true;
 $("#btnScan").after(b);
 const upd=()=>{b.disabled=$("#btnScan").disabled;};
 new MutationObserver(upd).observe($("#btnScan"),{attributes:true});
 setInterval(upd,600);
 let armed=false;
 $("#vidwrap").addEventListener("click",e=>{
  if(!armed)return;
  const r=$("#vidwrap").getBoundingClientRect();
  const x=Math.min(.99,Math.max(.01,(e.clientX-r.left)/r.width));
  const y=Math.min(.99,Math.max(.01,(e.clientY-r.top)/r.height));
  armed=false;b.textContent="🦅 Track object";
  toast(`target locked @ ${Math.round(x*100)}%,${Math.round(y*100)}%`,"ok");
  fetch(`/api/jobs/${jobId}/select`,{method:"POST",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify({mode:"track",point:{x,y}})})
   .then(()=>{setStep(2);
    $("#btnScan").dataset.scanning="1";updateScanBtn();});});
 b.onclick=()=>{
  if(activeJob&&$("#btnScan").dataset.scanning==="1")
   return toast("already scanning","err");
  armed=!armed;
  b.textContent=armed?"🎯 click the object…":"🦅 Track object";
  if(armed){PVpause();toast("pause on a clear frame, then CLICK the target","ok");}
  function PVpause(){try{$("#wizVideo").pause();}catch(e){}}};
})();
