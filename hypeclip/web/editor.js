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
