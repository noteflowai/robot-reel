const $=id=>document.getElementById(id);
document.querySelectorAll('button,input,select').forEach(el=>el.disabled=true);
let lab=null,condition='camera-viewpoints',sample=0,playing=false,origin=0,startSample=0,raf=0;
let selectionGeneration=0;
const mediaCache=new Map();
const videos=[$('reference'),$('challenge')],chosen=()=>lab.runs.find(r=>r.condition.name===condition);
function pause(){playing=false;cancelAnimationFrame(raf);$('play').textContent='Play recorded pair';}
function restore(){
 const params=new URLSearchParams(location.hash.slice(1));
 if(['camera-viewpoints','light-conditions'].includes(params.get('condition')))condition=params.get('condition');
 const frame=Number(params.get('sample'));
 if(Number.isInteger(frame)&&frame>=0&&frame<=220)sample=frame;
}
function seek(video,frame,steps){
 const time=Math.min(frame,steps)/20;
 if(video.readyState>=1&&Math.abs(video.currentTime-time)>.012)video.currentTime=time;
}
function render(updateHash=true){
 if(!lab)return;
 const run=chosen(),maximum=Math.max(77,run.steps);sample=Math.min(sample,maximum);
 $('condition').value=condition;$('sample').max=maximum;$('sample').value=sample;
 $('sample').setAttribute('aria-valuetext',`Source sample ${sample} of ${maximum}, ${(sample/20).toFixed(2)} seconds`);
 $('clock').textContent=`${sample} / ${maximum} · ${(sample/20).toFixed(2)} s`;
 $('previous').disabled=sample===0;$('next').disabled=sample===maximum;
 $('challenge-title').textContent=run.condition.category;
 $('challenge-label').textContent=`${run.task_success?'Success':'Step limit'} · ${run.steps} actions`;
 $('challenge-label').dataset.success=String(run.task_success);
 $('result').textContent=run.task_success?'Success':'Step limit';
 $('duration').textContent=`${run.steps} actions · ${(run.steps/20).toFixed(2)} simulated seconds`;
 $('reference-clock').textContent=sample>=77?'Episode ended · holding sample 77':`Recorded sample ${sample}`;
 $('challenge-clock').textContent=sample>=run.steps?`Episode ended · holding sample ${run.steps}`:`Recorded sample ${sample}`;
 $('trace').href=`${condition}/run.json`;$('video').href=`${condition}/rollout.mp4`;
 seek(videos[0],sample,77);seek(videos[1],sample,run.steps);
 if(updateHash)try{history.replaceState(null,'',`#${new URLSearchParams({condition,sample:String(sample)})}`);}catch{}
}
async function loadVideo(video,relative){
 if(video.dataset.recording===relative&&video.readyState>=1)return;
 let source=mediaCache.get(relative);
 if(!source){
  source=fetch(relative).then(async response=>{
   if(!response.ok)throw new Error('A recorded video is unavailable');
   const blob=await response.blob();
   if(blob.size>20*1024*1024)throw new Error('Recording exceeds the supported media size');
   return URL.createObjectURL(new Blob([blob],{type:'video/mp4'}));
  });
  mediaCache.set(relative,source);
 }
 const url=await source;
 await new Promise((resolve,reject)=>{
  const ready=()=>{cleanup();resolve();},failed=()=>{cleanup();reject(new Error('The browser could not decode a recording'));};
  const cleanup=()=>{video.removeEventListener('loadedmetadata',ready);video.removeEventListener('error',failed);};
  video.addEventListener('loadedmetadata',ready,{once:true});video.addEventListener('error',failed,{once:true});
  video.dataset.recording=relative;video.src=url;video.load();
 });
}
async function select(){
 pause();
 const generation=++selectionGeneration;
 document.querySelectorAll('button,input,select').forEach(el=>el.disabled=true);
 $('status').textContent='Loading the complete recorded pair for reliable frame seeking…';
 videos[1].poster=`${condition}/poster.png`;
 try{
  await Promise.all([loadVideo(videos[0],'baseline/rollout.mp4'),loadVideo(videos[1],`${condition}/rollout.mp4`)]);
  if(generation!==selectionGeneration)return;
  document.querySelectorAll('button,input,select').forEach(el=>el.disabled=false);
  render();$('status').textContent='Recorded pair ready. Earlier episodes hold their final source frame.';
 }catch(error){$('status').textContent=`${error.message}. Use the original video download links below.`;}
}
function tick(now){
 if(!playing)return;
 sample=Math.min(Math.max(77,chosen().steps),startSample+Math.floor((now-origin)/1000*20));
 render(false);
 if(sample===Math.max(77,chosen().steps)){pause();render();}else raf=requestAnimationFrame(tick);
}
for(const video of videos){
 video.addEventListener('loadedmetadata',()=>render(false));
 video.addEventListener('error',()=>{pause();$('status').textContent='A recording could not load. The source files and download links remain available.';});
}
$('play').onclick=()=>{
 if(!lab)return;
 if(playing){pause();render();return;}
 if(sample===Math.max(77,chosen().steps))sample=0;
 playing=true;startSample=sample;origin=performance.now();$('play').textContent='Pause';raf=requestAnimationFrame(tick);
};
$('condition').onchange=()=>{condition=$('condition').value;sample=0;select();};
$('sample').oninput=()=>{pause();sample=Number($('sample').value);render();};
$('previous').onclick=()=>{pause();sample=Math.max(0,sample-1);render();};
$('next').onclick=()=>{pause();sample=Math.min(Math.max(77,chosen().steps),sample+1);render();};
$('reference-end').onclick=()=>{pause();sample=77;render();};
$('end').onclick=()=>{pause();sample=chosen().steps;render();};
$('share').onclick=async()=>{pause();render();try{await navigator.clipboard.writeText(location.href);$('status').textContent='Copied this condition and source sample.';}catch{$('status').textContent=`Copy the address from your browser: ${location.href}`;}};
window.addEventListener('hashchange',()=>{restore();if(lab)select();});
document.addEventListener('visibilitychange',()=>{if(document.hidden){pause();render();}});
restore();
fetch('lab.json').then(response=>{if(!response.ok)throw new Error('Recording metadata unavailable');return response.json();}).then(data=>{
 if(data.schema!=='robot-reel.libero-plus-site.v1')throw new Error('Unsupported recording');
 lab=data;select();
}).catch(error=>{$('status').textContent=`${error.message}. Use the source downloads and methods below.`;document.querySelectorAll('button,input,select').forEach(el=>el.disabled=true);});
