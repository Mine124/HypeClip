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
 auto_render:$("#optAuto")?$("#optAuto").checked:true};}

function toast(msg,cls=""){const t=document.createElement("div");
 t.className="toast "+cls;t.textContent=msg;$("#toasts").append(t);
 setTimeout(()=>{t.style.opacity=0;setTimeout(()=>t.remove(),300)},3800);}

fetch("/api/meta").then(r=>r.json()).then(m=>{
 $("#engineDot").className="dot ok";$("#engineTxt").textContent="v"+m.version;})
.catch(()=>{$("#engineDot").className="dot bad";});
$("#folderBtn").onclick=()=>fetch("/api/meta").then(r=>r.json()).then(m=>
 fetch("/api/reveal",{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({path:m.out_dir})}));

/* ---------- wizard show/hide ---------- */
function openWizard(){$("#wiz").classList.remove("hidden");}
function closeWizard(){$("#wiz").classList.add("hidden");}
$("#wizClose").onclick=closeWizard;
$("#wiz").addEventListener("mousedown",e=>{
 if(e.target.id==="wiz")closeWizard();});
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

 /* autopilot: jump straight to step 4 when render begins */
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
 const grid=$(sel);if(!grid||grid.querySelec
