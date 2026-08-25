const $=s=>document.querySelector(s);
const qs=new URLSearchParams(location.search);
const file=qs.get("file");
function toast(msg,cls=""){const t=document.createElement("div");
 t.className="toast "+cls;t.textContent=msg;$("#toasts").append(t);
 setTimeout(()=>{t.style.opacity=0;setTimeout(()=>t.remove(),300)},3800);}

let DUR=0;
async function init(){
 const clips=await(await fetch("/api/editor/clips")).json();
 const mine=clips.find(c=>c.file===file)||clips[0];
 if(!mine){$("#statusLine").textContent="no clips yet - generate some first";return;}
 $("#clipName").textContent=mine.file;
 $("#pv").src=mine.url;DUR=mine.duration;
 $("#t1").value=DUR.toFixed(1);
 const edl=await(await fetch("/api/editor/edl?file="+encodeURIComponent(mine.file))).json();
 if(edl&&edl.t0!==undefined){
  for(const[k,id]of Object.entries({t0:"t0",t1:"t1",speed:"speed",brightness:"bright",
   contrast:"contrast",saturation:"sat",volume_db:"vol",fade_in:"fin",fade_out:"fout",
   aspect:"aspect"})){if(edl[k]!==undefined)$("#"+id).value=edl[k];}
  if(edl.mute)$("#mute").checked=true;if(edl.enhance)$("#enhance").checked=true;
  const tx=edl.texts||[];
  if(tx[0]){$("#txt1").value=tx[0].text||"";$("#y1").value=tx[0].y||85;$("#tt1").value=tx[0].t1||3;}
  if(tx[1]){$("#txt2").value=tx[1].text||"";$("#y2").value=tx[1].y||15;$("#tt2").value=tx[1].t1||3;}
  syncSliders();updateSel();}
}
$("#setIn").onclick=()=>{$("#t0").value=$("#pv").currentTime.toFixed(1);updateSel();};
$("#setOut").onclick=()=>{$("#t1").value=$("#pv").currentTime.toFixed(1);updateSel();};
$("#playSel").onclick=()=>{
 const a=parseFloat($("#t0").value),b=Math.min(parseFloat($("#t1").value)||DUR,DUR);
 $("#pv").currentTime=a;$("#pv").play();
 clearTimeout(window.__stopT);
 window.__stopT=setTimeout(()=>$("#pv").pause(),Math.max(0,(b-a))*1000);};
function updateSel(){
 const a=parseFloat($("#t0").value)||0,b=Math.min(parseFloat($("#t1").value)||DUR,DUR);
 $("#selInfo").textContent=`selection: ${(b-a).toFixed(1)}s`;}
["t0","t1"].forEach(id=>$("#"+id).addEventListener("change",updateSel));

function syncSliders(){
 paint($("#speed"),v=>v.toFixed(2)+"×");
 paint($("#bright"),v=>(+v).toFixed(2));
 paint($("#contrast"),v=>(+v).toFixed(2));
 paint($("#sat"),v=>(+v).toFixed(2));}
function paint(el,fmt){
 const mn=+el.min,mx=+el.max,v=+el.value;
 el.style.setProperty("--fill",((v-mn)/(mx-mn)*100)+"%");
 const o=el.closest(".slider")?.querySelector(".val");
 if(o)o.textContent=fmt(v);}
["speed","bright","contrast","sat"].forEach(id=>{
 $("#"+id).addEventListener("input",()=>syncSliders());});
syncSliders();

function collect(){
 return{
  t0:+$("#t0").value||0, t1:+$("#t1").value||undefined,
  speed:+$("#speed").value,
  brightness:+$("#bright").value, contrast:+$("#contrast").value,
  saturation:+$("#sat").value, aspect:$("#aspect").value,
  enhance:$("#enhance").checked,
  texts:[
   $("#txt1").value.trim()?{text:$("#txt1").value.trim(),y:+$("#y1").value,
    t1:+$("#tt1").value,color:"#FFFFFF"}:null,
   $("#txt2").value.trim()?{text:$("#txt2").value.trim(),y:+$("#y2").value,
    t1:+$("#tt2").value,color:"#FFFFFF"}:null].filter(Boolean),
  mute:$("#mute").checked, volume_db:+$("#vol").value,
  fade_in:+$("#fin").value, fade_out:+$("#fout").value};}

$("#renderBtn").onclick=async()=>{
 const btn=$("#renderBtn");btn.disabled=true;btn.textContent="rendering…";
 $("#statusLine").textContent="saving edit + rendering on the server…";
 const edl=collect();
 await fetch("/api/editor/save",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({file,edl})});
 try{
  const res=await(await fetch("/api/editor/render",{method:"POST",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify({file,edl})})).json();
  const tick=setInterval(async()=>{
   const s=await(await fetch("/api/editor/jobs/"+res.job_id)).json();
   if(s.state==="done"){clearInterval(tick);
    btn.disabled=false;btn.textContent="💾 Render edited clip 🎬";
    $("#statusLine").textContent="your edit is ready 👇";
    $("#resultBox").classList.remove("hidden");
    $("#resultVid").src=s.result.url;
    $("#dlBtn").href=s.result.url;$("#dlBtn").download=s.result.file;
    toast("edit rendered 🎬","ok");}
   else if(s.state==="error"){clearInterval(tick);
    btn.disabled=false;btn.textContent="💾 Render edited clip 🎬";
    $("#statusLine").textContent="render failed: "+s.error;
    toast(s.error,"err");}},1500);
 }catch(err){btn.disabled=false;toast(String(err),"err");}
};
init();
/* ======== ✂ Open-in-editor buttons + 🧠 Learner panel ======== */
(function(){
 /* edit buttons on every clip card */
 const st=document.createElement("style");st.textContent=`
 .lr-btn{position:fixed;left:20px;bottom:64px;z-index:45}
 .lr-panel{position:fixed;left:20px;bottom:116px;z-index:46;width:340px;
  background:#0d1019f5;border:1px solid rgba(255,255,255,.12);border-radius:16px;
  padding:16px;display:none;box-shadow:0 24px 60px -12px #000d;
  backdrop-filter:blur(14px);transform-origin:bottom left;
  animation:menuIn .35s cubic-bezier(.34,1.56,.64,1)}
 .lr-panel.open{display:block}
 .lr-panel input{width:100%;background:#0b0d15;color:#fff;border:1px solid
  rgba(255,255,255,.13);border-radius:9px;padding:9px 11px;outline:none;font-size:13px}`;
 document.head.append(st);

 function watch(gridId){
  const g=document.getElementById(gridId);if(!g)return;
  const deco=()=>g.querySelectorAll(".clip:not([data-edit])").forEach(card=>{
   card.dataset.edit="1";
   const btns=card.querySelector(".btns"),f=card.dataset.f;if(!btns||!f)return;
   const b=document.createElement("button");b.className="icon-btn";
   b.textContent="✂ edit";
   b.onclick=()=>open(`/static/editor.html?file=${encodeURIComponent(f)}`,"_blank");
   btns.prepend(b);});
  deco();new MutationObserver(deco).observe(g,{childList:true});}
 watch("clipsGrid");watch("wizClips");

 /* learner panel */
 const lb=document.createElement("button");lb.className="mini-btn lr-btn";
 lb.textContent="🧠 Learner";document.body.append(lb);
 const lp=document.createElement("div");lp.className="lr-panel";
 lp.innerHTML=`<b style="font-size:13px">📈 Teach it what works</b>
  <p class="hint">Post a clip, then paste its link here. After
  <b>3+</b>, the AI retunes clip length &amp; hype-zone picks automatically.</p>
  <div style="display:flex;gap:8px;margin-top:10px">
  <input id="lrUrl" placeholder="https://tiktok.com/... or youtube.com/..."/>
  <button class="mini-btn accent" id="lrAdd">Track</button></div>
  <div id="lrOut" class="hint" style="margin-top:12px"></div>`;
 document.body.append(lp);
 lb.onclick=()=>lp.classList.toggle("open");

 async function refreshLr(){
  const ins=await(await fetch("/api/learn/insights")).json();
  let html=ins.trained
   ?`<b class="green">trained on ${ins.samples} clips</b><br/>
     prefers ≈<b>${ins.best_len}s</b> · sweet spot ≈<b>${Math.round(ins.best_pos*100)}%</b> into streams`
   :`${ins.message}<br/><span class="dim">${ins.samples}/${ins.need}</span>`;
  $("#lrOut").innerHTML=html;}
 refreshLr();

 $("#lrAdd").onclick=async()=>{
  const u=$("#lrUrl").value.trim();if(!u)return toast("paste the posted clip's link","err");
  const r=await(await fetch("/api/learn/record",{method:"POST",
   headers:{"Content-Type":"application/json"},body:JSON.stringify({url:u})}));
  const d=await r.json();
  if(!r.ok)return toast(d.detail||"couldn't read that link","err");
  $("#lrUrl").value="";
  toast("tracked: "+(d.title||"clip").slice(0,40),"ok");
  if(d.trained)toast(`🧠 learner updated — now prefers ${d.best_len}s @ ${Math.round(d.best_pos*100)}%`,"ok");
  refreshLr();};
})();
