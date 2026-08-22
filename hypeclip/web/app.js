const $=s=>document.querySelector(s), $$=s=>document.querySelectorAll(s);
let jobId=null, timer=null;
const uploaded={music:null,wm:null};

/* ---------- sliders ---------- */
const OUT_MAP={optDur:"#durOut",optPre:"#preOut",optSens:"#senOut",
  optCool:"#coolOut",optZoomStr:"#zsOut",optShake:"#shOut",
  optSfxVol:"#svOut",optMusVol:"#mvOut"};
function paint(el){
  const min=+el.min||0,max=+el.max||100;
  el.style.setProperty("--fill",((el.value-min)/(max-min)*100)+"%");
  const sel=OUT_MAP[el.id];
  if(sel){const o=$(sel);
    if(sel==="#svOut"||sel==="#mvOut")
      o.textContent=(+el.value>=0?"+":"")+el.value;
    else o.textContent=el.value;}
}
$$("input[type=range]").forEach(el=>{
  el.addEventListener("input",()=>paint(el)); paint(el);});

/* ---------- presets ---------- */
const PRESETS={
 tiktok:{aspect:"9:16",CapStyle:"karaoke",Zoom:true,ZoomStr:65,Shake:45,Beat:true,
   Flash:true,Look:"capcut",Bloom:true,SfxVol:6,Dur:30,Grain:false,Vig:false},
 cinematic:{aspect:"16:9",CapStyle:"clean",Look:"cinematic",Bloom:true,Grain:true,
   Vig:true,Zoom:true,ZoomStr:30,Shake:0,Beat:false,SfxVol:0,Dur:60},
 gaming:{aspect:"16:9",CapStyle:"tiktok",Look:"capcut",Zoom:true,ZoomStr:75,
   Shake:65,Beat:true,Flash:true,Bloom:true,SfxVol:8,Dur:35},
 podcast:{aspect:"16:9",CapStyle:"clean",Look:"none",Bloom:false,Grain:false,
   Vig:false,Zoom:false,Shake:0,Beat:false,Flash:false,SfxVol:-4,Dur:60},
};
const ALIAS={mode:"Mode",max_clips:"Clips",clip_duration:"Dur",pre_roll:"Pre",
 hype_threshold:"Sens",cooldown:"Cool",max_height:"Height",fps:"Fps",
 zoom_punch:"Zoom",zoom_strength:"ZoomStr",shake:"Shake",beat_sync:"Beat",
 flash_intro:"Flash",fx_look:"Look",bloom:"Bloom",grain:"Grain",vignette:"Vig",
 caption_style:"CapStyle",sfx_volume_db:"SfxVol",music_volume_db:"MusVol"};

let activePreset="tiktok";
function markCustom(){if(activePreset==="custom")return;
 $$("#presets button").forEach(x=>x.classList.remove("active"));
 $("#presets button[data-p=custom]").classList.add("active");activePreset="custom";}
$$("#presets button").forEach(b=>b.onclick=()=>{
 $$("#presets button").forEach(x=>x.classList.remove("active"));
 b.classList.add("active");activePreset=b.dataset.p;
 const pr=PRESETS[activePreset];
 if(pr){applyOpts(pr);toast("Preset: "+b.textContent.trim());}});
function applyOpts(o){
 for(const[k,v]of Object.entries(o)){
  if(k==="aspect"){setAspect(v);continue;}
  const el=$("#opt"+ALIAS[k]);if(!el)continue;
  if(el.type==="checkbox")el.checked=!!v;
  else{el.value=v;if(el.type==="range")paint(el);}}}
function setAspect(a){
 $$("#segAspect button").forEach(x=>x.classList.toggle("active",x.dataset.a===a));}
$$("#segAspect button").forEach(b=>b.onclick=()=>{setAspect(b.dataset.a);markCustom();});
$$(".card input,.card select,.card textarea").forEach(el=>{
 if(el.closest("#presets"))return;
 el.addEventListener("change",e=>{if(e.target.id!=="")markCustom();});});

/* ---------- gather options ---------- */
function opts(){return{
 mode:$("#optMode").value,max_clips:+$("#optClips").value,
 clip_duration:+$("#optDur").value,pre_roll:+$("#optPre").value,
 hype_threshold:+$("#optSens").value,cooldown:+$("#optCool").value,
 max_height:+$("#optHeight").value,fps:+$("#optFps").value,
 zoom_punch:$("#optZoom").checked,zoom_strength:+$("#optZoomStr").value/100,
 shake:+$("#optShake").value/100,beat_sync:$("#optBeat").checked,
 flash_intro:$("#optFlash").checked,fx_look:$("#optLook").value,
 bloom:$("#optBloom").checked,grain:$("#optGrain").checked,
 vignette:$("#optVig").checked,
 aspect:$("#segAspect button.active").dataset.a,
 smart_reframe:$("#optReframe").checked,progress_bar:$("#optBar").checked,
 title_text:$("#optTitle").value,
 autocaptions:$("#optCaps").checked,caption_style:$("#optCapStyle").value,
 whisper_model:$("#optWhisper").value,sfx_enabled:$("#optSfx").checked,
 sfx_volume_db:+$("#optSfxVol").value,music_volume_db:+$("#optMusVol").value,
 duck_music:$("#optDuck").checked,
 music_file:uploaded.music||"",watermark_file:uploaded.wm||"",
};}

/* ---------- uploads ---------- */
$("#musicFile").onchange=async e=>{const f=e.target.files[0];if(!f)return;
 const fd=new FormData();fd.append("file",f);
 const r=await(await fetch("/api/upload?kind=music",{method:"POST",body:fd})).json();
 uploaded.music=r.path;toast("music uploaded","ok");};
$("#wmFile").onchange=async e=>{const f=e.target.files[0];if(!f)return;
 const fd=new FormData();fd.append("file",f);
 const r=await(await fetch("/api/upload?kind=watermark",{method:"POST",body:fd})).json();
 uploaded.wm=r.path;toast("watermark uploaded","ok");};

/* ---------- toasts ---------- */
function toast(msg,cls=""){const t=document.createElement("div");
 t.className="toast "+cls;t.textContent=msg;$("#toasts").append(t);
 setTimeout(()=>{t.style.opacity=0;setTimeout(()=>t.remove(),300)},3800);}

/* ---------- engine status ---------- */
fetch("/api/meta").then(r=>r.json()).then(m=>{
 $("#engineDot").className="dot ok";
 $("#engineTxt").textContent="v"+m.version+(m.nvenc?" GPU":"");
}).catch(()=>{$("#engineDot").className="dot bad";
 $("#engineTxt").textContent="offline";});
$("#folderBtn").onclick=()=>fetch("/api/meta").then(r=>r.json())
 .then(m=>fetch("/api/reveal",{method:"POST",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify({path:m.out_dir})}));

/* ---------- job lifecycle ---------- */
async function start(){
 const url=$("#urlInput").value.trim();
 if(!url)return toast("paste a YouTube link first","err");
 const res=await fetch("/api/jobs",{method:"POST",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify({url,options:opts()})});
 if(!res.ok)return toast("failed to start job","err");
 jobId=(await res.json()).job_id;
 $("#clipsGrid").innerHTML="";
 $("#statusWrap").classList.remove("hidden");
 $("#stopBtn").classList.remove("hidden");$("#goBtn").disabled=true;
 clearInterval(timer);timer=setInterval(poll,1500);poll();toast("job started");}
async function stop(){if(jobId)await fetch("/api/jobs/"+jobId,{method:"DELETE"});}
async function poll(){
 if(!jobId)return;
 let j;try{j=await(await fetch("/api/jobs/"+jobId)).json();}catch(e){return;}
 renderStatus(j);drawChart(j.series||{},j.moments||[]);
 const lg=$("#log"),stick=lg.scrollTop+lg.clientHeight>=lg.scrollHeight-40;
 lg.textContent=(j.logs||[]).join("\n");
 if(stick)lg.scrollTop=lg.scrollHeight;
 (j.clips||[]).forEach(c=>{
   if(!$(`[data-f="${CSS.escape(c.file)}"]`))addClip(c);});
 if(["done","error","stopped"].includes(j.state)){
   clearInterval(timer);timer=null;
   $("#goBtn").disabled=false;$("#stopBtn").classList.add("hidden");
   if(j.state==="done")toast("all clips ready!","ok");
   if(j.state==="error")toast(j.error,"err");}}
function renderStatus(j){
 const pct=Math.round((j.progress||0)*100);
 $("#pfill").style.width=pct+"%";$("#pct").textContent=pct+"%";
 $("#jobTitle").textContent=j.title||"";
 let act=null;
 $$(".step").forEach(st=>{st.classList.remove("active","done");
   if(j.stage&&j.stage.startsWith(st.dataset.s))act=st;});
 if(act)act.classList.add("active");
 if(j.state==="done"){
   $$(".step").forEach(st=>st.classList.add("done"));}}
function addClip(c){
 $("#emptyClips").classList.add("hidden");
 const mm=Math.floor(c.start/60),ss=String(Math.round(c.start%60)).padStart(2,"0");
 const el=document.createElement("div");el.className="clip";el.dataset.f=c.file;
 el.innerHTML=`<video src="${c.url}" preload="metadata" muted loop playsinline></video>
   <div class="meta">${c.score!==""?`<span class="badge">score ${c.score}</span>`:""}
   ${c.start!==""?`<span>@ ${mm}:${ss}</span>`:""}<span>${c.duration}s</span>
   <div class="btns"><a class="icon-btn" href="${c.url}" download="${c.file}">save</a>
   <button class="icon-btn" data-reveal="${c.file}">folder</button></div></div>`;
 const chips=document.createElement("div");chips.className="exp-row";
 [["tiktok","TT"],["shorts","Shorts"],["reels","Reels"],["x","X"]].forEach(
  ([id,label])=>{const b=document.createElement("button");
   b.className="exp-chip";b.textContent=label;
   b.onclick=()=>doExport(b,id,c.file);chips.append(b);});
 el.querySelector(".meta").after(chips);
 const v=el.querySelector("video");
 el.onmouseenter=()=>v.play().catch(()=>{});
 el.onmouseleave=()=>{v.pause();v.currentTime=0;};
 el.querySelector("[data-reveal]").onclick=()=>{
   fetch("/api/reveal_clip",{method:"POST",
     headers:{"Content-Type":"application/json"},
     body:JSON.stringify({file:c.file})});};
 $("#clipsGrid").prepend(el);}

/* ---------- platform exports ---------- */
async function doExport(btn,plat,file){
 btn.classList.add("busy");btn.disabled=true;
 try{
  const res=await(await fetch("/api/export",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({file,platform:plat})})).json();
  const tick=setInterval(async()=>{
    const st=await(await fetch("/api/export/"+res.export_id)).json();
    if(st.state==="done"){clearInterval(tick);
      btn.classList.remove("busy");btn.classList.add("ok");
      toast(plat.toUpperCase()+" export ready","ok");addClip(st.result);}
    else if(st.state==="error"){clearInterval(tick);
      btn.classList.remove("busy");toast(st.error,"err");}},1500);
 }catch(e){btn.classList.remove("busy");toast(String(e),"err");}}

/* ---------- hype chart ---------- */
function drawChart(series,moments){
 const cv=$("#chart"),ctx=cv.getContext("2d"),dpr=devicePixelRatio||1;
 cv.width=cv.clientWidth*dpr;cv.height=170*dpr;
 ctx.clearRect(0,0,cv.width,cv.height);
 const{t=[],score=[]}=series;if(t.length<2)return;
 const maxS=Math.max(...score,0.001),W=cv.width,H=cv.height,pad=14*dpr;
 const X=i=>pad+i/(t.length-1)*(W-2*pad),Y=v=>H-pad-(v/maxS)*(H-2*pad);
 const grd=ctx.createLinearGradient(0,0,0,H);
 grd.addColorStop(0,"#8b5cf688");grd.addColorStop(1,"#8b5cf600");
 ctx.beginPath();ctx.moveTo(X(0),H-pad);
 t.forEach((_,i)=>ctx.lineTo(X(i),Y(score[i])));
 ctx.lineTo(X(t.length-1),H-pad);ctx.closePath();ctx.fillStyle=grd;ctx.fill();
 ctx.beginPath();
 t.forEach((_,i)=>i?ctx.lineTo(X(i),Y(score[i])):ctx.moveTo(X(0),Y(score[0])));
 ctx.strokeStyle="#a78bfa";ctx.lineWidth=1.6*dpr;
 ctx.shadowColor="#8b5cf6";ctx.shadowBlur=8*dpr;ctx.stroke();ctx.shadowBlur=0;
 const t0=t[0],t1=t[t.length-1]||1;
 (moments||[]).forEach(m=>{
  const x1=X(Math.max(0,(m.start-t0)/(t1-t0))*(t.length-1)),
        x2=X(Math.min(1,(m.end-t0)/(t1-t0))*(t.length-1));
  ctx.fillStyle="#fb3b6422";ctx.fillRect(x1,pad*.3,x2-x1,H-pad*1.3);
  ctx.fillStyle="#fb3b64";
  ctx.font=(10*dpr)+"px sans-serif";
  ctx.fillText(m.score,x1+3,pad*.9);});}

/* ---------- updates + AI patch studio ---------- */
let manifestCache=null;
fetch("/api/meta").then(r=>r.json()).then(m=>{
 $("#updCur").textContent="v"+m.version;}).catch(()=>{});
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
 $("#updLatest").innerHTML=r.update_available
   ?` <b class="green">v${r.latest} available</b>`:" - latest";
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
     $("#instGo").classList.remove("hidden");toast("installer downloaded","ok");}
   if(s.state==="error"){clearInterval(tick);toast(s.error,"err");}},800);};
$("#instGo").onclick=async()=>{
 await fetch("/api/update/run_installer",{method:"POST"});
 toast("launching installer...");};
$("#remoteApply").onclick=async()=>{
 if(!manifestCache)return;
 $("#remoteApply").disabled=true;
 const r=await fetch("/api/update/apply_remote",{method:"POST",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify({manifest:{files:manifestCache.files}})});
 if(r.ok){toast("hot-fix applied - restarting...","ok");
   setTimeout(()=>fetch("/api/system/restart",{method:"POST"}),800);}
 else toast("apply failed","err");};

async function loadPatchFiles(){
 try{
  const list=await(await fetch("/api/update/files")).json();
  $("#patchFile").innerHTML=list.map(f=>`<option>${f.path}</option>`).join("");
 }catch(e){}
}
loadPatchFiles();
$("#patchLoad").onclick=async()=>{
 const f=$("#patchFile").value;if(!f)return;
 const d=await(await fetch("/api/update/file?path="+encodeURIComponent(f))).json();
 $("#patchCode").value=d.code;$("#patchMsg").textContent="";};
$("#patchPrompt").onclick=async()=>{
 const f=$("#patchFile").value;if(!f)return;
 let code=$("#patchCode").value.trim();
 if(!code)code=(await(await fetch("/api/update/file?path="+
   encodeURIComponent(f))).json()).code;
 const goal=$("#patchGoal").value.trim()||"improve robustness and performance";
 const prompt=
"You are maintaining HypeClip, a Python 3.10 FastAPI app that turns YouTube "+
"livestream chats into edited clips (yt-dlp, chat-downloader, faster-whisper, "+
"ffmpeg filtergraphs, pydub).\n"+
`Rewrite the module \"${f}\" to: ${goal}\n`+
"Rules: keep all public names/imports compatible with the rest of the package; "+
"stdlib + these deps only (numpy, yt-dlp, chat_downloader, faster_whisper, "+
"pydub, fastapi, uvicorn, PIL, cv2 optional); no new dependencies; "+
"Windows-friendly paths.\n"+
"Return ONLY the complete new file contents, no markdown fences.\n\n"+
"=== CURRENT SOURCE ===\n"+code;
 await navigator.clipboard.writeText(prompt);
 toast("AI prompt copied - paste into ChatGPT/Claude/Gemini","ok");};
$("#patchValidate").onclick=async()=>{
 const r=await(await fetch("/api/update/validate",{method:"POST",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify({code:$("#patchCode").value})})).json();
 $("#patchMsg").textContent=r.ok?"syntax OK":r.error;
 $("#patchMsg").className=r.ok?"green":"red";};
$("#patchApply").onclick=async()=>{
 const f=$("#patchFile").value;
 const val=await(await fetch("/api/update/validate",{method:"POST",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify({code:$("#patchCode").value})})).json();
 if(!val.ok)return toast("fix syntax first: "+val.error,"err");
 const r=await fetch("/api/update/apply",{method:"POST",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify({path:f,code:$("#patchCode").value})});
 if(r.ok){toast("patch applied - restarting...","ok");
   setTimeout(()=>fetch("/api/system/restart",{method:"POST"}),800);}
 else toast("apply failed","err");};
async function refreshBackups(){
 try{
  const list=await(await fetch("/api/update/backups")).json();
  $("#bakCount").textContent=list.length;
  $("#bakList").innerHTML=list.map(b=>`<div class="bak">
    <span>${b.time}</span><code>${b.module}</code>
    <span>${(b.size/1024).toFixed(1)} KB</span>
    <button class="mini-btn" data-bak="${b.name}">restore</button></div>`).join("")
    ||'<span class="dim">no backups yet</span>';
  $$("#bakList [data-bak]").forEach(b=>b.onclick=async()=>{
    await fetch("/api/update/restore",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({name:b.dataset.bak})});
    setTimeout(()=>fetch("/api/system/restart",{method:"POST"}),600);});
 }catch(e){}
}
refreshBackups();

$("#goBtn").onclick=start;
$("#stopBtn").onclick=stop;
$("#urlInput").addEventListener("keydown",e=>{
 if(e.key==="Enter")start();});
addEventListener("keydown",e=>{
 if(e.ctrlKey&&e.key==="Enter")start();});