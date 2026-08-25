const $=s=>document.querySelector(s),$$=s=>document.querySelectorAll(s);
function toast(m,c=""){const t=document.createElement("div");t.className="toast "+c;
 t.textContent=m;$("#toasts").append(t);
 setTimeout(()=>{t.style.opacity=0;setTimeout(()=>t.remove(),300)},3800);}

let SEQ=[],SEL=-1,DUR=0,PV=$("#pv");
let UNDO=[],REDO=[];
const snapshot=()=>{UNDO.push(JSON.stringify(SEQ));if(UNDO.length>40)UNDO.shift();REDO=[];};
const undo=()=>{if(!UNDO.length)return;REDO.push(JSON.stringify(SEQ));
 SEQ=JSON.parse(UNDO.pop());SEL=Math.min(SEL,SEQ.length-1);drawSeq();};
const redo=()=>{if(!REDO.length)return;UNDO.push(JSON.stringify(SEQ));
 SEQ=JSON.parse(REDO.pop());drawSeq();};
$("#undoBtn").onclick=undo;$("#redoBtn").onclick=redo;

/* ---------- tabs ---------- */
$$("#tabs .tab").forEach(b=>b.onclick=()=>{
 $$("#tabs .tab").forEach(x=>x.classList.remove("active"));
 $$(".tabpane").forEach(x=>x.classList.remove("active"));
 b.classList.add("active");$("#tp-"+b.dataset.p).classList.add("active");});

/* ---------- init: load first clip ---------- */
(async function(){
 const clips=await(await fetch("/api/editor/clips")).json();
 if(!clips.length){toast("generate clips first","err");return;}
 const mine=clips.find(c=>c.file===new URLSearchParams(location.search).get("file"))||clips[0];
 PV.src=mine.url;DUR=mine.duration;
 SEQ=[newClipObj(mine.file,mine.duration)];
 drawSeq();refreshLib();refreshMus();
})();
function newClipObj(file,d){return{file,t0:0,t1:+d.toFixed(1),speed:1,reverse:false,
 transform:{},crop:{},color:{},effects:{},chroma:{},audio:{},
 kf_opacity:[],kf_volume:[],fade_in:0,fade_out:0,interp60:false};}

/* ---------- sequence strip ---------- */
function drawSeq(){
 const s=$("#seq");s.innerHTML="";
 SEQ.forEach((c,i)=>{
  const d=document.createElement("div");
  d.className="seqchip"+(i===SEL?" sel":"");
  d.innerHTML=`<b>${(c.file||"clip").slice(0,18)}</b>
   ${(+c.t1-(+c.t0)).toFixed(1)}s${c.speed!==1?" @"+c.speed+"×":""}
   <div class="ops"><button data-l="◀">◀</button><button data-r="▶">▶</button>
   <button data-x="✕">✕</button></div>`;
  d.onclick=e=>{
   if(e.target.dataset.l){snapshot();if(i>0){[SEQ[i-1],SEQ[i]]=[SEQ[i],SEQ[i-1]];drawSeq();}return;}
   if(e.target.dataset.r){snapshot();if(i<SEQ.length-1){[SEQ[i+1],SEQ[i]]=[SEQ[i],SEQ[i+1]];drawSeq();}return;}
   if(e.target.dataset.x){snapshot();SEQ.splice(i,1);SEL=Math.min(SEL,SEQ.length-1);drawSeq();return;}
   SEL=i;loadClipToUI(c);drawSeq();};
  s.append(d);});
 $("#selInfo").textContent=`${SEQ.length} clip(s)`;
}
function loadClipToUI(c){
 $("#t-set")&&0;
 const g=(id)=>$(id);
 g("#tfX").value=c.transform.x||0;g("#tfY").value=c.transform.y||0;
 g("#tfScale").value=c.transform.scale||1;g("#tfRot").value=c.transform.rotation||0;
 g("#tfFlip").value=c.transform.flip||"";g("#tfOp").value=c.transform.opacity??"";
 ["#crX","#crY","#crW","#crH"].forEach((id,k)=>{
  g(id).value=[c.crop?.x,c.crop?.y,c.crop?.w,c.crop?.h][k]||0;});
 g("#spd").value=c.speed;paintRange(g("#spd"),v=>(+v).toFixed(2)+"×");
 g("#rev").checked=!!c.reverse;g("#ip60").checked=!!c.interp60;
 const co=c.color||{};
 g("#coB").value=co.brightness||0;g("#coC").value=co.contrast||1;
 g("#coS").value=co.saturation||1;g("#coV").value=co.vibrance||0;
 g("#coH").value=co.hue||0;g("#coE").value=co.exposure||0;
 g("#coT").value=co.temperature||0;g("#coTn").value=co.tint||0;
 const st=c.effects||{};
 g("#fxBlur").value=st.blur||0;g("#fxSharp").value=st.sharpen||0;
 g("#fxGlow").checked=!!st.glow;g("#fxGrain").checked=!!st.grain;
 g("#fxPix").value=st.pixelate||0;g("#fxMos").value=st.mosaic||0;
 g("#fxVhs").checked=!!st.vhs;g("#fxRgb").value=st.rgbsplit||0;
 g("#fxEmboss").checked=!!st.emboss;g("#fxBox").checked=!!st.box_blur;
 const ck=c.chroma||{};g("#ckOn").checked=!!ck.enabled;
 g("#ckCol").value=ck.color||"green";g("#ckSim").value=ck.similarity??0.25;
 g("#ckSoft").value=ck.softness??0.1;g("#ckSpill").checked=ck.despill??true;
 const au=c.audio||{};
 g("#auV").value=au.volume_db||0;g("#auP").value=au.pan||0;
 g("#auPit").value=au.pitch||1;g("#auBa").value=au.bass||0;g("#auTr").value=au.treble||0;
 g("#auDn").checked=!!au.denoise;g("#auVo").checked=!!au.voice;
 g("#auCp").checked=!!au.compressor;g("#auLm").checked=!!au.limiter;
 g("#auNm").checked=!!au.normalize;g("#auMu").checked=!!au.mute;
 drawKf(c);}
function collectUI(){
 const c=SEQ[SEL];if(!c)return null;
 const num=(id,dflt)=>{const v=$(id).value;return v===""||v===undefined?dflt:+v;};
 c.transform={x:num("#tfX",0),y:num("#tfY",0),scale:num("#tfScale",1),
  rotation:num("#tfRot",0),flip:$("#tfFlip").value||null,
  opacity:$("#tfOp").value===""?null:num("#tfOp",1)};
 const cw=num("#crW",0),ch=num("#crH",0);
 c.crop=(cw||ch)?{x:num("#crX",0),y:num("#crY",0),w:cw,h:ch}:{};
 c.speed=+$("#spd").value;c.reverse=$("#rev").checked;c.interp60=$("#ip60").checked;
 c.color={brightness:num("#coB",0),contrast:num("#coC",1),
  saturation:num("#coS",1),vibrance:num("#coV",0),hue:num("#coH",0),
  exposure:num("#coE",0),temperature:num("#coT",0),tint:num("#coTn",0),
  lut_file:c.color?.lut_file||null,
  lift_gamma_gain:c.color?.lift_gamma_gain||null,
  whites_blacks:c.color?.whites_blacks||null};
 c.effects={blur:num("#fxBlur",0),sharpen:num("#fxSharp",0),
  glow:$("#fxGlow").checked,grain:$("#fxGrain").checked,
  pixelate:num("#fxPix",0)>0?num("#fxPix"):0,
  mosaic:num("#fxMos",0)>0?num("#fxMos"):0,
  vhs:$("#fxVhs").checked,rgbsplit:num("#fxRgb",0),
  emboss:$("#fxEmboss").checked,box_blur:$("#fxBox").checked};
 c.chroma={enabled:$("#ckOn").checked,color:$("#ckCol").value,
  similarity:+$("#ckSim").value,softness:+$("#ckSoft").value,
  despill:$("#ckSpill").checked};
 c.audio={volume_db:num("#auV",0),pan:num("#auP",0),pitch:num("#auPit",1),
  bass:num("#auBa",0),treble:num("#auTr",0),denoise:$("#auDn").checked,
  voice:$("#auVo").checked,compressor:$("#auCp").checked,
  limiter:$("#auLm").checked,normalize:$("#auNm").checked,mute:$("#auMu").checked};
 return c;}
$$(".tabpane input,.tabpane select").forEach(el=>
 el.addEventListener("change",()=>{collectUI();}));
function paintRange(el,fmt){
 const v=+el.value,mn=+el.min,mx=+el.max;
 el.style.setProperty("--fill",((v-mn)/(mx-mn)*100)+"%");
 el.closest(".slider")&&(el.closest(".slider").querySelector(".val")||
  {}).textContent!==undefined&&
  (el.closest(".slider").querySelector(".val").textContent=fmt(v));}
$("#spd").addEventListener("input",()=>paintRange($("#spd"),v=>(+v).toFixed(2)+"×"));
paintRange($("#spd"),v=>(+v).toFixed(2)+"×");

/* ---------- trim/split/dup/del ---------- */
$("#setIn").onclick=()=>{if(SEL<0)return;snapshot();
 SEQ[SEL].t0=+PV.currentTime.toFixed(1);drawSeq();};
$("#setOut").onclick=()=>{if(SEL<0)return;snapshot();
 SEQ[SEL].t1=+Math.min(PV.currentTime,DUR).toFixed(1);drawSeq();};
$("#splitBtn").onclick=()=>{if(SEL<0)return;snapshot();
 const c=JSON.parse(JSON.stringify(SEQ[SEL]));
 const mid=+PV.currentTime.toFixed(1);
 if(mid<=c.t0+0.3||mid>=c.t1-0.3)return toast("playhead inside clip first","err");
 const right=JSON.parse(JSON.stringify(c));right.t0=mid;c.t1=mid;
 SEQ.splice(SEL+1,0,right);drawSeq();toast("split ✓","ok");};
$("#dupBtn").onclick=()=>{if(SEL<0)return;snapshot();
 SEQ.splice(SEL+1,0,JSON.parse(JSON.stringify(SEQ[SEL])));drawSeq();};
$("#delBtn").onclick=()=>{if(SEL<0)return;snapshot();
 SEQ.splice(SEL,1);SEL=Math.max(0,SEL-1);drawSeq();};
$("#snap").addEventListener("change",e=>{window.__snap=e.target.checked;});

/* ---------- detections ---------- */
async function curFile(){return SEQ[Math.max(0,SEL)]?.file;}
$("#sceneBtn").onclick=async()=>{
 const f=await curFile();if(!f)return;toast("detecting scenes…");
 const d=await(await fetch("/api/editor/detect_scenes",{method:"POST",
  headers:{"Content-Type":"application/json"},body:JSON.stringify({file:f})})).json();
 drawMarkers(d.cuts.map(t=>({t,label:"scene"})));
 toast(`${d.cuts.length} scene cuts found`,"ok");};
$("#silenceBtn").onclick=async()=>{
 const f=await curFile();if(!f)return;toast("detecting silence…");
 const d=await(await fetch("/api/editor/detect_silence",{method:"POST",
  headers:{"Content-Type":"application/json"},body:JSON.stringify({file:f})})).json();
 drawMarkers(d.spans.map(([a,b])=>({t:a,label:`sil ${b-a}s`})));
 toast(`${d.spans.length} silent spans`,"ok");};
let MARKERS=[];
function drawMarkers(list){MARKERS=list;
 const m=$("#markers");m.innerHTML="";
 list.forEach(mk=>{const e=document.createElement("div");e.className="marker";
  e.style.left=Math.min(100,mk.t/Math.max(DUR,1)*100)+"%";
  e.title=mk.label+" @"+mk.t+"s";e.onclick=()=>{PV.currentTime=mk.t;};m.append(e);});}

/* ---------- playback ---------- */
$$("[data-rate]").forEach(b=>b.onclick=()=>{PV.playbackRate=+b.dataset.rate;});
addEventListener("keydown",e=>{
 if(/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName))return;
 if(e.code==="Space"){e.preventDefault();PV.paused?PV.play():PV.pause();}
 if(e.key==="j")PV.playbackRate=Math.max(.25,PV.playbackRate/2),PV.play();
 if(e.key==="l")PV.playbackRate=Math.min(4,PV.playbackRate*2),PV.play();
 if(e.key==="k"){PV.pause();PV.playbackRate=1;}
 if(e.key==="ArrowLeft")PV.currentTime-=1/30;
 if(e.key==="ArrowRight")PV.currentTime+=1/30;
 if(e.key==="i")$("#setIn").click();
 if(e.key==="o")$("#setOut").click();
 if(e.key==="s")$("#splitBtn").click();
 if(e.key==="Delete"||e.key==="Backspace")$("#delBtn").click();
 if(e.ctrlKey&&e.key==="z"){e.preventDefault();undo();}
 if(e.ctrlKey&&e.key==="y"){e.preventDefault();redo();}});

/* ---------- keyframes ---------- */
function drawKf(c){
 $("#kfoList").innerHTML=(c.kf_opacity||[]).map((k,i)=>
  `<div class="kf"><code>t=${k.t}s → opacity ${k.v}</code>
   <button class="mini-btn" data-o="${i}">✕</button></div>`).join("");
 $$("#kfoList [data-o]").forEach(b=>b.onclick=()=>{
  snapshot();c.kf_opacity.splice(+b.dataset.o,1);drawKf(c);});
 $("#kfvList").innerHTML=(c.kf_volume||[]).map((k,i)=>
  `<div class="kf"><code>t=${k.t}s → ${k.v}dB</code>
   <button class="mini-btn" data-v="${i}">✕</button></div>`).join("");
 $$("#kfvList [data-v]").forEach(b=>b.onclick=()=>{
  snapshot();c.kf_volume.splice(+b.dataset.v,1);drawKf(c);});}
$("#kfoAdd").onclick=()=>{const c=SEQ[SEL];if(!c)return;snapshot();
 (c.kf_opacity=c.kf_opacity||[]).push({t:+PV.currentTime.toFixed(1),
  v:+($("#kfoV").value||1)});
 c.kf_opacity.sort((a,b)=>a.t-b.t);drawKf(c);};
$("#kfvAdd").onclick=()=>{const c=SEQ[SEL];if(!c)return;snapshot();
 (c.kf_volume=c.kf_volume||[]).push({t:+PV.currentTime.toFixed(1),
  v:+($("#kfvV").value||0)});
 c.kf_volume.sort((a,b)=>a.t-b.t);drawKf(c);};

/* ---------- LUT + scopes ---------- */
$("#lutBtn").onclick=()=>$("#lutFile").click();
$("#lutFile").addEventListener("change",async e=>{
 const f=e.target.files[0];if(!f)return;
 const fd=new FormData();fd.append("file",f);
 const r=await(await fetch("/api/editor/import",{method:"POST",body:fd})).json();
 if(SEQ[SEL]){snapshot();(SEQ[SEL].color=SEQ[SEL].color||{}).lut_file=r.file;}
 $("#lutName").textContent=" "+r.file;toast("LUT loaded","ok");});
$$("[data-scope]").forEach(b=>b.onclick=async()=>{
 const f=await curFile();if(!f)return;
 const r=await(await fetch(`/api/editor/scopes?file=${encodeURIComponent(f)}`
  +"&kind="+b.dataset.scope+"&t="+PV.currentTime.toFixed(1))).json();
 const img=$("#scopeImg");img.src=r.url;img.style.display="block";});

/* ---------- texts & overlays ---------- */
let TXT=[],OV=[];let pendingOv=null;
function txtRow(){
 const i=TXT.length;if(i>=6)return toast("6 max","err");
 TXT.push({text:"",y:85,t0:0,t1:3,size:64,color:"#FFFFFF",outline:true,
  shadow:true,bg:false});
 const row=document.createElement("div");
 row.className="grid";row.style.gridTemplateColumns="1fr 70px 70px 70px";
 row.innerHTML=`<input placeholder="text ${i+1}" data-t="${i}"/>
  <input type="number" data-y="${i}" value="85" min="2" max="96"/>
  <input type="number" data-s="${i}" value="64"/>
  <input type="number" data-e="${i}" value="3"/>`;
 $("#txtRows").append(row);
 row.querySelectorAll("input").forEach(inp=>inp.addEventListener("change",()=>{
  const k=i;TXT[k].text=row.querySelector("[data-t]").value;
  TXT[k].y=+row.querySelector("[data-y]").value;
  TXT[k].size=+row.querySelector("[data-s]").value;
  TXT[k].t1=+row.querySelector("[data-e]").value;}));}
$("#txtAdd").onclick=txtRow;
$$("[data-shape]").forEach(b=>b.onclick=async()=>{
 const r=await(await fetch("/api/editor/shape",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({kind:b.dataset.shape})})).json();
 pendingOv=r.file;$("#ovAdd").disabled=false;toast(r.file+" ready","ok");});
$("#ovFile").addEventListener("change",async e=>{
 const f=e.target.files[0];if(!f)return;
 const fd=new FormData();fd.append("file",f);
 const r=await(await fetch("/api/editor/import",{method:"POST",body:fd})).json();
 pendingOv=r.file;$("#ovAdd").disabled=false;});
$("#ovAdd").onclick=()=>{
 if(!pendingOv)return;
 OV.push({file:pendingOv,x:50,y:50,scale:30,t0:0,t1:0});
 pendingOv=null;$("#ovAdd").disabled=true;
 const row=document.createElement("div");
 row.className="grid";row.style.gridTemplateColumns="repeat(5,1fr)";
 const i=OV.length-1;
 row.innerHTML=`<input type="number" data-x="${i}" value="50"/>
  <input type="number" data-y="${i}" value="50"/>
  <input type="number" data-sc="${i}" value="30"/>
  <input type="number" data-t1="${i}" value="0" placeholder="end"/>
  <button class="mini-btn danger" data-rm="${i}">✕</button>`;
 $("#ovRows").append(row);
 row.querySelectorAll("input").forEach(inp=>inp.addEventListener("change",()=>{
  OV[i].x=+row.querySelector(`[data-x="${i}"]`).value;
  OV[i].y=+row.querySelector(`[data-y="${i}"]`).value;
  OV[i].scale=+row.querySelector(`[data-sc="${i}"]`).value;
  OV[i].t1=+row.querySelector(`[data-t1="${i}"]`).value||0;}));
 row.querySelector("[data-rm]").onclick=()=>{row.remove();OV[i]=null;};};

/* ---------- library + music ---------- */
async function refreshLib(){
 const q=$("#libQ").value.trim();
 const list=await(await fetch("/api/editor/library?q="+encodeURIComponent(q))).json();
 $("#libList").innerHTML=list.filter(x=>x.kind==="video").map(x=>
  `<span class="libitem" data-add="${x.url}" data-f="${x.dur||""}">
   🎞 ${x.file.slice(0,22)}</span>`).join("")||'<span class="dim">empty</span>';
 $$("#libList [data-add]").forEach(el=>el.onclick=async()=>{
  const url=el.dataset.add;
  const head=await fetch(url,{method:"HEAD"}).catch(()=>null);
  snapshot();
  SEQ.push(newClipObj(decodeURIComponent(url.split("/").pop()),
   Math.round((+(head?.headers.get("content-length")||0))/4e6)||30));
  SEL=SEQ.length-1;drawSeq();});}
$("#libQ").addEventListener("input",refreshLib);
$("#impFile").addEventListener("change",async e=>{
 const f=e.target.files[0];if(!f)return;
 const fd=new FormData();fd.append("file",f);
 await fetch("/api/editor/import",{method:"POST",body:fd});
 toast("imported "+f.name,"ok");refreshLib();});
async function refreshMus(){
 const q=$("#musQ").value.trim();
 const list=await(await fetch("/api/editor/library?q="+encodeURIComponent(q)
  +"&kind=audio")).json();
 $("#musList").innerHTML=list.map(x=>
  `<span class="libitem" data-mus="${x.file}">🎵 ${x.file.slice(0,24)}</span>`).join("")
  ||'<span class="dim">drop audio via Import ↑</span>';
 $$("#musList [data-mus]").forEach(el=>el.onclick=()=>{
  $("#musOn").checked=true;
  window.__music={file:el.dataset.mus};
  toast("music: "+el.dataset.mus,"ok");});}
$("#musRefresh").onclick=refreshMus;

/* ---------- autosave / recover ---------- */
const PKEY=new URLSearchParams(location.search).get("file")||"default";
function persist(){localStorage.setItem("hc_edl_"+PKEY,
 JSON.stringify({SEQ,TXT,OV,music:window.__music}));}
setInterval(()=>{if(SEQ.length)persist();},4000);
(function recover(){try{
 const d=JSON.parse(localStorage.getItem("hc_edl_"+PKEY)||"null");
 if(d&&d.SEQ?.length){SEQ=d.SEQ;TXT=d.TXT||[];OV=d.OV||[];
  window.__music=d.music;drawSeq();}}catch(e){}})();
$("#saveBtn").onclick=async()=>{
 await fetch("/api/editor/save",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({project:PKEY,data:{SEQ,TXT,OV,music:window.__music}})});
 persist();toast("project saved 💾","ok");};

/* ---------- render ---------- */
$("#renderAll").onclick=async()=>{
 collectUI();const btn=$("#renderAll");
 btn.disabled=true;btn.textContent="rendering…";
 $("#statusLine").textContent="";
 const payload={
  project:PKEY,
  clips:SEQ,
  transition:{type:$("#trType").value==="none"?"":$("#trType").value,
   dur:+$("#trDur").value},
  texts:TXT.filter(t=>t.text),
  overlays:OV.filter(Boolean),
  music:window.__music&&$("#musOn").checked?
   {...window.__music,volume_db:+$("#musV").value}:null,
  master:{normalize:$("#exNorm").checked},
  export:{format:$("#exFmt").value,aspect:$("#exAsp").value,
   fps:+$("#exFps").value,codec:$("#exCodec").value,
   crf:+$("#exCrf").value,abitrate:+$("#exAb").value,
   hardware:$("#exHw").checked}};
 try{
  const res=await(await fetch("/api/editor/render",{method:"POST",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify(payload)})).json();
  const tick=setInterval(async()=>{
   const s=await(await fetch("/api/editor/jobs/"+res.job_id)).json();
   s.logs.slice(-1).forEach(l=>$("#statusLine").textContent=l);
   if(s.state==="done"){clearInterval(tick);
    btn.disabled=false;btn.textContent="🎬 Render sequence";
    $("#resultBox").classList.remove("hidden");
    $("#resultVid").src=s.result.url;
    $("#dlBtn").href=s.result.url;$("#dlBtn").download=s.result.file;
    toast("sequence ready 🎬","ok");
    if($("#exTk").checked)fetch("/api/export",{method:"POST",
     headers:{"Content-Type":"application/json"},
     body:JSON.stringify({file:s.result.file,platform:"tiktok"})})
     .then(()=>toast("TikTok copy exporting 📦","ok"));}
   else if(s.state==="error"){clearInterval(tick);
    btn.disabled=false;btn.textContent="🎬 Render sequence";
    $("#statusLine").textContent=s.error;toast(s.error,"err");}},1600);
 }catch(err){btn.disabled=false;toast(String(err),"err");}
};
