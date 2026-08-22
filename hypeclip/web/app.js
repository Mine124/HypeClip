const $=s=>document.querySelector(s),$$=s=>document.querySelectorAll(s);
let jobId=null,timer=null,capTimer=null;
const uploaded={music:null,wm:null};

/* ---------- tabs ---------- */
$$(".tab").forEach(b=>b.onclick=()=>{
 $$(".tab").forEach(x=>x.classList.remove("active"));
 $$(".tab-panel").forEach(x=>x.classList.remove("active"));
 b.classList.add("active");$("#panel-"+b.dataset.tab).classList.add("active");});

/* ---------- sliders ---------- */
const OUT={optDur:"#durOut",optPre:"#preOut",optSens:"#senOut",optCool:"#coolOut",
 optZoomStr:"#zsOut",optShake:"#shOut",optSfxVol:"#svOut",optMusVol:"#mvOut"};
function paint(el){
 const min=+el.min||0,max=+el.max||100;
 el.style.setProperty("--fill",((el.value-min)/(max-min)*100)+"%");
 const sel=OUT[el.id];
 if(sel){const o=$(sel);
  o.textContent=(sel==="#svOut"||sel==="#mvOut")&&+el.value>=0?"+"+el.value:el.value;}}
$$("input[type=range]").forEach(el=>{
 el.addEventListener("input",()=>paint(el));paint(el);});

/* ---------- studio presets/options ---------- */
const PRESETS={
 tiktok:{aspect:"9:16",Look:"capcut",Bloom:true,Grain:false,Vig:false,Zoom:true,
  ZoomStr:65,Shake:45,Beat:true,Flash:true,SfxVol:6,Dur:30},
 cinematic:{aspect:"16:9",Look:"cinematic",Bloom:true,Grain:true,Vig:true,Zoom:true,
  ZoomStr:30,Shake:0,Beat:false,SfxVol:0,Dur:60},
 gaming:{aspect:"16:9",Look:"capcut",Bloom:true,Grain:false,Vig:false,Zoom:true,
  ZoomStr:75,Shake:65,Beat:true,Flash:true,SfxVol:8,Dur:35},
 podcast:{aspect:"16:9",Look:"none",Bloom:false,Grain:false,Vig:false,Zoom:false,
  Shake:0,Beat:false,Flash:false,SfxVol:-4,Dur:60}};
let activePreset="tiktok";
function markCustom(){if(activePreset==="custom")return;
 $$("#presets button").forEach(x=>x.classList.remove("active"));
 $("#presets button[data-p=custom]").classList.add("active");activePreset="custom";}
$$("#presets button").forEach(b=>b.onclick=()=>{
 $$("#presets button").forEach(x=>x.classList.remove("active"));
 b.classList.add("active");activePreset=b.dataset.p;
 const pr=PRESETS[activePreset];if(pr){setOpts(pr);toast("Preset applied");}});
function setOpts(o){for(const[k,v]of Object.entries(o)){
 if(k==="aspect"){$$("#segAspect button").forEach(x=>
   x.classList.toggle("active",x.dataset.a===v));continue;}
 const el=$("#opt"+k.charAt(0).toUpperCase()+k.slice(1));if(!el)continue;
 if(el.type==="checkbox")el.checked=!!v;
 else{el.value=v;if(el.type==="range")paint(el);}}}
$$("#segAspect button").forEach(b=>b.onclick=()=>{markCustom();
 $$("#segAspect button").forEach(x=>x.classList.remove("active"));
 b.classList.add("active");});

function opts(){return{
 mode:$("#optMode").value,max_clips:+$("#optClips").value,
 clip_duration:+$("#optDur").value,pre_roll:+$("#optPre").value,
 hype_threshold:+$("#optSens").value,cooldown:+$("#optCool").value,
 max_height:+$("#optHeight").value,fps:+$("#optFps").value,
 zoom_punch:$("#optZoom").checked,zoom_strength:+$("#optZoomStr").value/100,
 shake:+$("#optShake").value/100,beat_sync:$("#optBeat").checked,
 flash_intro:$("#optFlash").checked,fx_look:$("#optLook").value,
 bloom:$("#optBloom").checked,grain:$("#optGrain").checked,vignette:$("#optVig").checked,
 aspect:$("#segAspect button.active").dataset.a,smart_reframe:$("#optReframe").checked,
 progress_bar:$("#optBar").checked,title_text:$("#optTitle").value,
 autocaptions:$("#optCaps").checked,whisper_model:$("#optWhisper").value,
 sfx_enabled:$("#optSfx").checked,sfx_volume_db:+$("#optSfxVol").value,
 music_volume_db:+$("#optMusVol").value,duck_music:$("#optDuck").checked,
 music_file:uploaded.music||"",watermark_file:uploaded.wm||"",
 caption:capState};}

/* ---------- uploads/toasts/status ---------- */
function toast(msg,cls=""){const t=document.createElement("div");
 t.className="toast "+cls;t.textContent=msg;$("#toasts").append(t);
 setTimeout(()=>{t.style.opacity=0;setTimeout(()=>t.remove(),300)},3800);}
$("#musicFile").onchange=async e=>{const f=e.target.files[0];if(!f)return;
 const fd=new FormData();fd.append("file",f);
 const r=await(await fetch("/api/upload?kind=music",{method:"POST",body:fd})).json();
 uploaded.music=r.path;toast("Music uploaded","ok");};
$("#wmFile").onchange=async e=>{const f=e.target.files[0];if(!f)return;
 const fd=new FormData();fd.append("file",f);
 const r=await(await fetch("/api/upload?kind=watermark",{method:"POST",body:fd})).json();
 uploaded.wm=r.path;toast("Watermark uploaded","ok");};
fetch("/api/meta").then(r=>r.json()).then(m=>{
 $("#engineDot").className="dot ok";
 $("#engineTxt").textContent="v"+m.version+(m.nvenc?" GPU":"");})
.catch(()=>{$("#engineDot").className="dot bad";});
$("#folderBtn").onclick=()=>fetch("/api/meta").then(r=>r.json()).then(m=>
 fetch("/api/reveal",{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({path:m.out_dir})}));

/* ---------- caption designer ---------- */
let capState=null;
async function initCaptions(){
 capState=await(await fetch("/api/caption/defaults")).json();
 const keys=Object.keys(capState);
 keys.forEach(k=>{
  const el=$("#cap_"+k);if(!el)return;
  el.addEventListener("input",()=>{
   capState[k]=el.type==="checkbox"?el.checked:
    (el.type==="range"?+el.value:el.value);
   const o=$("#cap_"+k+"_o");
   if(o)o.textContent=el.type==="range"?el.value:"";
   scheduleCapPreview();});});
 await refreshCapPresets();
 scheduleCapPreview();}
function capPayload(){return{style:{...capState}};}
function scheduleCapPreview(){
 $("#capStatus").textContent="rendering...";
 clearTimeout(capTimer);capTimer=setTimeout(renderCapPreview,500);}
async function renderCapPreview(){
 try{
  const r=await(await fetch("/api/caption/preview",{method:"POST",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify(capPayload())})).json();
  $("#capVideo").src=r.url;$("#capStatus").textContent="";
 }catch(e){$("#capStatus").textContent="preview failed";}}
$("#capRerender").onclick=renderCapPreview;
async function refreshCapPresets(){
 const list=await(await fetch("/api/caption/presets")).json();
 $("#capPresetSel").innerHTML='<option value="">saved presets...</option>'+
  list.map(p=>`<option>${p.name}</option>`).join("");}
$("#capPresetSave").onclick=async()=>{
 const name=$("#capPresetName").value.trim();
 if(!name)return toast("Name your preset first","err");
 await fetch("/api/caption/presets",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({name,style:capState})});
 toast("Preset saved","ok");await refreshCapPresets();};
$("#capPresetLoad").onclick=async()=>{
 const name=$("#capPresetSel").value;if(!name)return;
 const all=await(await fetch("/api/caption/presets")).json();
 toast("Loaded: "+name);
 const r=await(await fetch("/api/caption/preview",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({style:{...capState,_load:name}})}));
 location.reload();};
$("#capPresetDel").onclick=async()=>{
 const name=$("#capPresetSel").value;if(!name)return;
 await fetch("/api/caption/presets?name="+encodeURIComponent(name),
  {method:"DELETE"});
 toast("Deleted");await refreshCapPresets();};

/* NOTE on preset load: presets store full style; simplest reliable load: */
window.addEventListener("DOMContentLoaded",initCaptions);

/* ---------- jobs ---------- */
async function start(){
 const url=$("#urlInput").value.trim();
 if(!url)return toast("paste a YouTube link first","err");
 const res=await fetch("/api/jobs",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({url,options:opts()})});
 if(!res.ok)return toast("failed to start job","err");
 jobId=(await res.json()).job_id;
 $("#clipsGrid").innerHTML="";$("#statusWrap").classList.remove("hidden");
 $("#stopBtn").classList.remove("hidden");$("#goBtn").disabled=true;
 clearInterval(timer);timer=setInterval(poll,1500);poll();toast("Job started");}
$("#stopBtn").onclick=()=>jobId&&fetch("/api/jobs/"+jobId,{method:"DELETE"});
async function poll(){
 if(!jobId)return;
 let j;try{j=await(await fetch("/api/jobs/"+jobId)).json();}catch(e){return;}
 const pct=Math.round((j.progress||0)*100);
 $("#pfill").style.width=pct+"%";$("#pct").textContent=pct+"%";
 $("#jobTitle").textContent=j.title||"";
 let act=null;
 $$(".step").forEach(st=>{st.classList.remove("active","done");
  if(j.stage&&j.stage.startsWith(st.dataset.s))act=st;});
 if(act)act.classList.add("active");
 if(j.state==="done")$$(".step").forEach(st=>st.classList.add("done"));
 const lg=$("#log"),stick=lg.scrollTop+lg.clientHeight>=lg.scrollHeight-40;
 lg.textContent=(j.logs||[]).join("\n");
 if(stick)lg.scrollTop=lg.scrollHeight;
 (j.clips||[]).forEach(c=>{
  if(!$(`[data-f="${CSS.escape(c.file)}"]`))addClip(c);});
 if(["done","error","stopped"].includes(j.state)){
  clearInterval(timer);timer=null;$("#goBtn").disabled=false;
  $("#stopBtn").classList.add("hidden");
  if(j.state==="done")toast("All clips ready!","ok");
  if(j.state==="error")toast(j.error,"err");}}
function addClip(c){
 $("#emptyClips")&&$("#emptyClips").classList.add("hidden");
 const mm=Math.floor((c.start||0)/60),ss=String(Math.round((c.start||0)%60)).padStart(2,"0");
 const el=document.createElement("div");el.className="clip";el.dataset.f=c.file;
 el.innerHTML=`<video src="${c.url}" preload="metadata" muted loop playsinline></video>
  <div class="meta">${c.score!==""?`<span class="badge">score ${c.score}</span>`:""}
  ${c.start!==""?`<span>@${mm}:${ss}</span>`:""}<span>${c.duration}s</span>
  <div class="btns"><a class="icon-btn" href="${c.url}" download="${c.file}">save</a>
  <button class="icon-btn" data-reveal="${c.file}">folder</button></div></div>`;
 const chips=document.createElement("div");chips.className="exp-row";
 [["tiktok","TT"],["shorts","Shorts"],["reels","Reels"],["x","X"]].forEach(([id,l])=>{
  const b=document.createElement("button");b.className="exp-chip";b.textContent=l;
  b.onclick=()=>doExport(b,id,c.file);chips.append(b);});
 el.querySelector(".meta").after(chips);
 const v=el.querySelector("video");
 el.onmouseenter=()=>v.play().catch(()=>{});
 el.onmouseleave=()=>{v.pause();v.currentTime=0;};
 el.querySelector("[data-reveal]").onclick=()=>fetch("/api/reveal_clip",
  {method:"POST",headers:{"Content-Type":"application/json"},
   body:JSON.stringify({file:c.file})});
 $("#clipsGrid").prepend(el);}
async function doExport(btn,plat,file){
 btn.disabled=true;try{
 const res=await(await fetch("/api/export",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({file,platform:plat})})).json();
 const tick=setInterval(async()=>{
  const st=await(await fetch("/api/export/"+res.export_id)).json();
  if(st.state==="done"){clearInterval(tick);btn.classList.add("ok");
   toast(plat.toUpperCase()+" export ready","ok");addClip(st.result);}
  else if(st.state==="error"){clearInterval(tick);btn.disabled=false;
   toast(st.error,"err");}},1500);}catch(e){btn.disabled=false;toast(String(e),"err");}}

/* ---------- chart ---------- */
function drawChart(series,moments){
 const cv=$("#chart"),ctx=cv.getContext("2d"),dpr=devicePixelRatio||1;
 cv.width=cv.clientWidth*dpr;cv.height=150*dpr;ctx.clearRect(0,0,cv.width,cv.height);
 const{t=[],score=[]}=series;if(t.length<2)return;
 const maxS=Math.max(...score,.001),W=cv.width,H=cv.height,pad=12*dpr;
 const X=i=>pad+i/(t.length-1)*(W-2*pad),Y=v=>H-pad-(v/maxS)*(H-2*pad);
 const grd=ctx.createLinearGradient(0,0,0,H);
 grd.addColorStop(0,"#7c5cff77");grd.addColorStop(1,"#7c5cff00");
 ctx.beginPath();ctx.moveTo(X(0),H-pad);
 t.forEach((_,i)=>ctx.lineTo(X(i),Y(score[i])));
 ctx.lineTo(X(t.length-1),H-pad);ctx.closePath();ctx.fillStyle=grd;ctx.fill();
 ctx.beginPath();
 t.forEach((_,i)=>i?ctx.lineTo(X(i),Y(score[i])):ctx.moveTo(X(0),Y(score[0])));
 ctx.strokeStyle="#a78bfa";ctx.lineWidth=1.5*dpr;ctx.stroke();
 const t0=t[0],t1=t[t.length-1]||1;
 (moments||[]).forEach(m=>{
  const x1=X(Math.max(0,(m.start-t0)/(t1-t0))*(t.length-1)),
        x2=X(Math.min(1,(m.end-t0)/(t1-t0))*(t.length-1));
  ctx.fillStyle="#fb3b6422";ctx.fillRect(x1,0,x2-x1,H-pad);});}

/* ---------- code studio ---------- */
async function loadFiles(){
 try{
  const list=await(await fetch("/api/update/files")).json();
  $("#patchFile").innerHTML=list.map(f=>`<option>${f.path}</option>`).join("");
 }catch(e){}}
loadFiles();
$("#patchLoad").onclick=async()=>{
 const d=await(await fetch("/api/update/file?path="+
  encodeURIComponent($("#patchFile").value))).json();
 $("#patchCode").value=d.code;$("#patchMsg").textContent="";};
$("#patchPrompt").onclick=async()=>{
 const f=$("#patchFile").value;
 let code=$("#patchCode").value.trim();
 if(!code)code=(await(await fetch("/api/update/file?path="+
  encodeURIComponent(f))).json()).code;
 const goal=$("#patchGoal").value.trim()||"improve robustness and performance";
 const prompt=`You are maintaining HypeClip, a Python FastAPI app that turns YouTube livestream chats into edited clips.\nRewrite the file \"${f}\" to: ${goal}\nRules: keep public names compatible; deps allowed: numpy, yt-dlp, chat_downloader, faster_whisper, pydub, fastapi, uvicorn, PIL; Windows-friendly.\nReturn ONLY the complete new file contents.\n\n=== CURRENT SOURCE ===\n${code}`;
 await navigator.clipboard.writeText(prompt);
 toast("AI prompt copied","ok");};
$("#patchValidate").onclick=async()=>{
 const f=$("#patchFile").value;
 if(!f.endsWith(".py")){$("#patchMsg").textContent="web file - no syntax check";
  $("#patchMsg").className="dim";return;}
 const r=await(await fetch("/api/update/validate",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({path:f,code:$("#patchCode").value})})).json();
 $("#patchMsg").textContent=r.ok?"syntax OK":r.error;
 $("#patchMsg").className=r.ok?"green":"red";};
async function applyAndRestart(){
 setTimeout(()=>fetch("/api/system/restart",{method:"POST"}),900);}
$("#patchApply").onclick=async()=>{
 const val=await(await fetch("/api/update/validate",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({path:$("#patchFile").value,code:$("#patchCode").value})})).json();
 if(!val.ok)return toast("Fix syntax: "+val.error,"err");
 const r=await fetch("/api/update/apply",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({path:$("#patchFile").value,code:$("#patchCode").value})});
 if(r.ok){toast("Applied - restarting...","ok");applyAndRestart();}
 else toast("Apply failed","err");};
$("#bulkApply").onclick=async()=>{
 const txt=$("#bulkPatch").value;
 if(!txt.includes("=== FILE:"))return toast('Use "=== FILE: path ===" sections',"err");
 const r=await fetch("/api/update/apply_many",{method:"POST",
  headers:{"Content-Type":"application/json"},body:JSON.stringify({text:txt})});
 if(r.ok){const d=await r.json();
  toast(`Applied ${d.files.length} file(s) - restarting`,"ok");applyAndRestart();}
 else toast((await r.json()).detail,"err");};
async function refreshBackups(){
 try{
  const list=await(await fetch("/api/update/backups")).json();
  $("#bakCount").textContent=list.length;
  $("#bakList").innerHTML=list.map(b=>`<div class="bak">
   <span>${b.time}</span><code>${b.module}</code>
   <button class="mini-btn" data-bak="${b.name}">restore</button></div>`).join("")
   ||'<span class="dim">no backups yet</span>';
  $$("#bakList [data-bak]").forEach(b=>b.onclick=async()=>{
   await fetch("/api/update/restore",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({name:b.dataset.bak})});
   toast("Restored - restarting");applyAndRestart();});
 }catch(e){}}
refreshBackups();

/* ---------- updates ---------- */
let manifestCache=null;
fetch("/api/meta").then(r=>r.json()).then(m=>{$("#updCur").textContent="v"+m.version;});
$("#updUrl").value=localStorage.getItem("hc_manifest")||"";
$("#updUrl").addEventListener("change",e=>
 localStorage.setItem("hc_manifest",e.target.value));
$("#updCheck").onclick=async()=>{
 $("#updNotes").textContent="checking...";
 const r=await(await fetch("/api/update/check",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({url:$("#updUrl").value.trim()||null})})).json();
 if(!r.ok){$("#updNotes").textContent=r.error;return;}
 manifestCache=r;
 $("#updLatest").innerHTML=r.update_available?
  ` <b class="green">v${r.latest} available</b>`:" - latest";
 $("#updNotes").textContent=r.notes||"";
 $("#updDl").classList.toggle("hidden",!r.update_available);
 $("#remoteApply").classList.toggle("hidden",
  !(r.update_available&&(r.files||[]).length));
 $("#updNextVer").textContent=r.latest;};
$("#updDl").onclick=()=>{
 if(!manifestCache||!manifestCache.installer_url)
  return toast("no installer URL in manifest","err");
 fetch("/api/update/dl_start",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({url:manifestCache.installer_url})});
 const tick=setInterval(async()=>{
  const s=await(await fetch("/api/update/dl_status")).json();
  $("#dlFill").style.width=Math.round(s.frac*100)+"%";
  if(s.state==="done"){clearInterval(tick);
   $("#instGo").classList.remove("hidden");toast("Installer downloaded","ok");}
  if(s.state==="error"){clearInterval(tick);toast(s.error,"err");}},800);};
$("#instGo").onclick=async()=>{await fetch("/api/update/run_installer",{method:"POST"});};
$("#remoteApply").onclick=async()=>{
 if(!manifestCache)return;
 const r=await fetch("/api/update/apply_remote",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({manifest:{files:manifestCache.files}})});
 if(r.ok){toast("Hot-fix applied","ok");applyAndRestart();}
 else toast("Failed","err");};

$("#goBtn").onclick=start;
$("#urlInput").addEventListener("keydown",e=>e.key==="Enter"&&start());
addEventListener("keydown",e=>{if(e.ctrlKey&&e.key==="Enter")start();});
