/* Recorded poses and camera calibration; this module never runs a policy. */
const $ = id => document.getElementById(id);
const point = ([x,y,z]) => [x,z,-y];
const poseObject = (object, pose) => {
 object.position.set(...pose.slice(0,3));
 object.quaternion.set(pose[4],pose[5],pose[6],pose[3]);
 object.updateMatrixWorld(true);
};

export async function mountMotion({manifest,getVariant,getApp,changeRepresentation,writeHash}) {
 async function bytes(path, expected) {
  const response=await fetch(path);
  if(!response.ok)throw new Error(`${path}: HTTP ${response.status}`);
  const data=await response.arrayBuffer();
  if(!crypto.subtle)throw new Error('Source checks need HTTPS or a localhost server');
  const sha=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',data)),b=>b.toString(16).padStart(2,'0')).join('');
  if(data.byteLength!==expected.bytes||sha!==expected.sha256)throw new Error(`Source check failed for ${path}`);
  return data;
 }
 const record=JSON.parse(new TextDecoder().decode(await bytes('motion/motion.json',manifest.files['motion/motion.json'])));
 if(record.schema!=='robot-reel.scene-motion-site.v1')throw new Error('Unsupported recorded-motion data');
 const cache=new Map(),mediaCache=new Map(),videos=[$('motion-simulation'),$('motion-blender')],pendingSeeks=new WeakMap(),independentVideos=new WeakSet();
 const state={
  frame:0,view:'recorded',quality:'full',playing:false,trace:null,variant:getVariant(),
  model:null,bounds:null,bodyNodes:[],boundNodes:[],path:null,contacts:null,
  camera:null,cameraHelper:null,scale:null,attached:null,attachedVariant:null,
  samples:[],lastRender:0,warmUntil:0,adaptations:[],renderFps:null,videoSource:'',videosRequested:false,
  record,viewport:null,switching:false,mediaError:null,
 };
 let animation=0,playStart=0,playFrame=0,selection=0,geometryPromise=null,boundsData=null;
 const error = problem => {$('motion-readiness').textContent=problem.message||String(problem);};
 const total = () => record.cases[getVariant()].frames;
 const fps = () => record.plan.sample_hz;
 function restore() {
  const params=new URLSearchParams(location.hash.slice(1)),value=params.get('frame');
  if(value!==null&&/^\d+$/.test(value))state.frame=Math.min(Number(value),total()-1);
  if(['recorded','orbit','scene'].includes(params.get('view')))state.view=params.get('view');
 }
 restore();
 document.querySelectorAll('.motion-only').forEach(element=>element.hidden=false);
 if(matchMedia('(max-width:700px)').matches)document.querySelector('.motion-details').open=false;
 document.querySelector('h1').innerHTML='Put the replay<br>back in the <span>scene.</span>';
 document.querySelector('.tag').textContent='RECORDED MOTION · NATIVE READBACK';
 document.querySelector('.intro').textContent='Follow a recorded Microduck on captured coastal terrain. Keep the original camera, switch scene representations, and match the source frame in Blender. Every pose, contact and timestamp comes from the saved simulation.';
 $('load').textContent='Open the matched 3D replay';
 $('share').textContent='Copy frame link';
 $('poster').src=`motion/${state.variant}/poster.png`;
 $('poster').alt='Recorded Microduck on the captured coast, rendered in Blender from the source camera.';
 const initialBytes=['motion/robot.glb',`motion/${state.variant}/trace.json`,`${state.variant}/scene.glb`,'vendor/three.module.min.js','vendor/three.core.min.js'].reduce((sum,name)=>sum+(manifest.files[name]?.bytes||0),0);
 document.querySelector('#overlay p').textContent=`The initial geometry, trace and core libraries total ${(initialBytes/1048576).toFixed(1)} MiB, plus controls and metadata. Load recordings below to review without 3D.`;

 function mediaSources() {
  const variant=getVariant();
  if(state.videoSource===variant)return;
  state.videoSource=variant;state.videosRequested=false;
  videos.forEach((video,i)=>{
   pendingSeeks.delete(video);independentVideos.delete(video);
   video.pause();video.removeAttribute('src');video.load();delete video.dataset.recording;
   if(i)video.poster=`motion/${variant}/poster.png`;
  });
  for(const [id,file] of [['motion-trace','trace.json'],['motion-usd','motion.usdc'],['motion-check','blender-check.json']])$(id).href=`motion/${variant}/${file}`;
  $('motion-fingerprint').textContent=`${variant} trace SHA-256: ${record.cases[variant].trace.sha256}`;
 }
 async function loadVideos(variant) {
  await Promise.all(videos.map(async(video,i)=>{
   const relative=`${variant}/${i?'blender':'simulation'}.mp4`;
   if(!mediaCache.has(relative)){
    const pending=bytes(`motion/${relative}`,record.files[relative]).then(data=>URL.createObjectURL(new Blob([data],{type:'video/mp4'})));
    mediaCache.set(relative,pending);pending.catch(()=>mediaCache.delete(relative));
   }
   const url=await mediaCache.get(relative);
   if(variant!==getVariant())return;
   if(video.dataset.recording===relative&&video.readyState>=1)return;
   await new Promise((resolve,reject)=>{
    const cleanup=()=>{clearTimeout(timer);video.removeEventListener('loadedmetadata',ready);video.removeEventListener('error',failed);};
    const ready=()=>{cleanup();resolve();},failed=()=>{cleanup();reject(new Error(`Could not decode ${relative}`));};
    const timer=setTimeout(()=>{cleanup();reject(new Error(`Recording load timed out: ${relative}`));},20000);
    video.addEventListener('loadedmetadata',ready);video.addEventListener('error',failed);
    video.dataset.recording=relative;video.src=url;video.load();
   });
  }));
 }
 function syncVideos() {
  const time=(state.frame+.25)/fps();
  videos.forEach(video=>{
   independentVideos.delete(video);
   if(!video.paused)video.pause();
   pendingSeeks.set(video,time);
    if(video.readyState>=2&&!video.seeking){
    if(Math.abs(video.currentTime-time)>.003)video.currentTime=time;
    else pendingSeeks.delete(video);
   }
  });
  $('simulation-frame').textContent=`Source frame ${state.frame}`;
  $('blender-frame').textContent=`Blender frame ${state.frame+1}`;
 }
 videos.forEach(video=>{
  video.addEventListener('loadedmetadata',syncVideos);
  for(const event of ['loadeddata','canplay'])video.addEventListener(event,()=>{
   if(pendingSeeks.has(video)&&!independentVideos.has(video))syncVideos();
  });
  video.addEventListener('seeked',()=>{
   const target=pendingSeeks.get(video);
   if(target===undefined)return;
   if(Math.abs(video.currentTime-target)>.003)video.currentTime=target;
   else pendingSeeks.delete(video);
  });
  video.addEventListener('play',()=>{
   pendingSeeks.delete(video);
   independentVideos.add(video);
   if(state.playing){state.playing=false;cancelAnimationFrame(animation);animation=0;labels();}
   $('motion-readiness').textContent='Native video playback is independent. Step a source frame above to resynchronize both recordings and the scene.';
  });
  video.addEventListener('seeking',()=>{
   if(!pendingSeeks.has(video))independentVideos.add(video);
  });
  video.addEventListener('timeupdate',()=>{
   if(independentVideos.has(video)){
    $(video===videos[0]?'simulation-frame':'blender-frame').textContent=`Independent video clock ${video.currentTime.toFixed(2)} s`;
   }
  });
  video.addEventListener('error',()=>{$('motion-readiness').textContent='A video could not load. Original traces and frame downloads remain available; reload the recording to retry.';});
 });
 function labels() {
  $('motion-frame').max=String(total()-1);$('motion-frame').value=String(state.frame);
  const frame=state.trace?.frames[state.frame];
  $('motion-label').textContent=`${state.frame} / ${total()-1}${frame?` · ${frame.sim_time_s.toFixed(3)} s`:''} · Blender frame ${state.frame+1}`;
  $('motion-clock').textContent=frame?`${frame.sim_time_s.toFixed(3)} s · step ${frame.physics_step}`:'—';
  $('motion-root').textContent=frame?frame.qpos.slice(0,3).map(v=>v.toFixed(4)).join(', '):'—';
  $('motion-contacts').textContent=frame?String(frame.terrain_contacts.length):'—';
  $('motion-policy').textContent=frame?`${frame.policy_call} / ${state.trace.policy_calls.length-1}`:'—';
  $('motion-previous').disabled=!frame||state.frame===0;
  $('motion-next').disabled=!frame||state.frame===total()-1;
  $('motion-play').disabled=!frame;
  $('motion-play').textContent=state.playing?'Pause':'Play';
  $('motion-end').disabled=!frame;
  $('motion-frame').disabled=!frame;
  $('motion-export').disabled=!frame;
  $('camera-recorded').setAttribute('aria-pressed',String(state.view==='recorded'));
  $('camera-orbit').setAttribute('aria-pressed',String(state.view==='orbit'));
 }
 async function ensureTrace() {
  const variant=getVariant(),ticket=selection;
  mediaSources();
  if(!cache.has(variant)){
   $('motion-readiness').textContent=`Loading and checking the ${variant} recording…`;
   const pending=bytes(`motion/${variant}/trace.json`,record.files[`${variant}/trace.json`])
    .then(data=>JSON.parse(new TextDecoder().decode(data)));
   cache.set(variant,pending);
   pending.catch(()=>cache.delete(variant));
  }
  const trace=await cache.get(variant);
  if(trace.case!==variant||trace.schema!=='robot-reel.scene-motion.v1'||trace.frames.length!==record.cases[variant].frames)throw new Error('The trace does not match the selected experiment');
  if(ticket!==selection||variant!==getVariant())return false;
  state.trace=trace;state.variant=variant;state.frame=Math.min(state.frame,trace.frames.length-1);
  $('motion-load').textContent='Reload recordings';
  $('motion-readiness').textContent=`Checked ${trace.frames.length} source frames and ${trace.policy_calls.length} policy calls. Both videos follow the selected frame.`;
  if(!state.videosRequested){
   state.videosRequested=true;state.mediaError=null;
   try{await loadVideos(variant);}catch(problem){state.mediaError=problem.message;state.videosRequested=false;}
  }
  if(ticket!==selection||variant!==getVariant())return false;
  updateGeometry();labels();syncVideos();
  if(state.mediaError)$('motion-readiness').textContent=`Recording unavailable: ${state.mediaError}. The trace and 3D frame remain available; use Reload recordings to retry.`;
  return true;
 }
 function pause() {
  state.playing=false;cancelAnimationFrame(animation);animation=0;
  videos.forEach(video=>video.pause());labels();
 }
 function seek(frame,{share=true}={}) {
  state.frame=Math.max(0,Math.min(Math.round(frame),total()-1));
  updateGeometry();labels();syncVideos();
  if(share)writeHash();
 }
 function tick(now) {
  if(!state.playing)return;
  if(document.hidden){pause();writeHash();return;}
  const frame=playFrame+Math.floor((now-playStart)/1000*fps());
  if(frame!==state.frame)seek(frame,{share:false});
  if(frame>=total()-1){pause();writeHash();return;}
  animation=requestAnimationFrame(tick);
 }
 async function play() {
  if(state.playing){pause();writeHash();return;}
  if(!state.trace||state.variant!==getVariant())await ensureTrace();
  if(!state.trace)return;
  if(state.frame===total()-1)seek(0);
  videos.forEach(video=>video.pause());
  state.playing=true;playStart=performance.now();playFrame=state.frame;labels();
  animation=requestAnimationFrame(tick);
 }
 function recordedCamera(app) {
  const {THREE}=app,source=state.trace.camera;
  const camera=new THREE.PerspectiveCamera(source.vertical_fov_degrees,source.width/source.height,.02,150);
  camera.position.set(...point(source.position_m));
  const axes=source.axes_world.map(axis=>new THREE.Vector3(...point(axis)));
  camera.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(...axes));
  camera.updateMatrixWorld(true);return camera;
 }
 function view(mode,{share=true}={}) {
  state.view=mode;
  const app=getApp();
  if(app&&state.trace&&state.attached){
   app.controls.autoRotate=false;$('rotate').setAttribute('aria-pressed','false');$('rotate').textContent='Turntable';
   app.controls.enabled=mode!=='recorded';
   if(mode==='recorded'){
    app.camera.position.copy(state.camera.position);app.camera.quaternion.copy(state.camera.quaternion);
    app.camera.fov=state.camera.fov;app.camera.near=state.camera.near;app.camera.far=state.camera.far;
   }else if(mode==='orbit'){
    const center=new app.THREE.Vector3(...point(state.trace.frames[state.frame].qpos.slice(0,3)));
    app.controls.target.copy(center);app.camera.position.copy(center).add(new app.THREE.Vector3(.75,.5,.8));
    app.camera.near=.02;app.controls.update();
   }else app.reset();
   resize();updateGeometry();
  }
  labels();if(share)writeHash();warmup();
 }
 function resize() {
  const app=getApp();if(!app)return;
  const {width,height}=$('stage').getBoundingClientRect();
  if(state.view==='recorded'&&state.camera){
   const aspect=state.camera.aspect,w=Math.min(width,height*aspect),h=w/aspect;
   state.viewport={x:(width-w)/2,y:(height-h)/2,width:w,height:h};
   app.camera.aspect=aspect;
  }else{state.viewport={x:0,y:0,width,height};app.camera.aspect=width/height;}
  app.camera.updateProjectionMatrix();app.camera.updateMatrixWorld(true);
 }
 function warmup() {state.samples=[];state.lastRender=0;state.warmUntil=performance.now()+3000;}
 function updateGeometry() {
  const app=getApp();if(!app||!state.trace||!state.attached)return;
  if(state.switching)return;
  const frame=state.trace.frames[state.frame];
  state.bodyNodes.forEach((node,i)=>poseObject(node,frame.body_poses[i]));
  state.boundNodes.forEach((node,i)=>poseObject(node,frame.body_poses[i]));
  if(state.path)state.path.visible=$('show-path').checked;
  if(state.contacts){
   const attribute=state.contacts.geometry.getAttribute('position');
   frame.terrain_contacts.forEach((contact,i)=>attribute.setXYZ(i,...point(contact.position_m)));
   attribute.needsUpdate=true;
   state.contacts.geometry.setDrawRange(0,frame.terrain_contacts.length);
   state.contacts.visible=$('show-contacts').checked&&frame.terrain_contacts.length>0;
  }
  if(state.cameraHelper)state.cameraHelper.visible=state.view!=='recorded'&&$('show-camera').checked;
  if(state.model)state.model.visible=state.quality==='full';
  if(state.bounds)state.bounds.visible=state.quality==='bounds';
 }
 async function makeFullGeometry(app) {
  if(state.model)return;
  if(!geometryPromise){
   geometryPromise=bytes('motion/robot.glb',record.files['robot.glb']).then(buffer=>app.loader.parseAsync(buffer,''))
    .then(gltf=>{
     const model=gltf.scene,nodes=state.trace.bodies.map(name=>model.getObjectByName(name));
     if(nodes.some(node=>!node))throw new Error('Recorded robot body is absent from the GLB');
     state.model=model;state.bodyNodes=nodes;app.scene.add(model);updateGeometry();
    }).catch(problem=>{geometryPromise=null;throw problem;});
  }
  await geometryPromise;
 }
 async function attach(app) {
  if(state.attached===app&&state.trace&&state.attachedVariant===getVariant()){updateGeometry();return;}
  if(!await ensureTrace())return;
  if(!state.attached){
   const {THREE}=app;
   app.controls.minDistance=.15;
   boundsData=JSON.parse(new TextDecoder().decode(await bytes('motion/body-bounds.json',record.files['body-bounds.json'])));
   const group=new THREE.Group();group.rotation.x=-Math.PI/2;
   const material=new THREE.MeshBasicMaterial({color:'#98c7db',wireframe:true});
   state.boundNodes=boundsData.bodies.map(body=>{
    const node=new THREE.Group(),dimensions=body.max_m.map((v,i)=>v-body.min_m[i]);
    const mesh=new THREE.Mesh(new THREE.BoxGeometry(...dimensions),material);
    mesh.position.set(...body.min_m.map((v,i)=>(v+body.max_m[i])/2));
    node.add(mesh);node.name=body.name;group.add(node);return node;
   });
   state.bounds=group;app.scene.add(group);
   state.contacts=new THREE.Points(new THREE.BufferGeometry(),new THREE.PointsMaterial({color:'#ffbd7c',size:.016,depthTest:false}));
   state.contacts.renderOrder=3;state.contacts.frustumCulled=false;app.scene.add(state.contacts);state.attached=app;
  }
  const contactCapacity=Math.max(1,...state.trace.frames.map(frame=>frame.terrain_contacts.length));
  if((state.contacts.geometry.getAttribute('position')?.count||0)<contactCapacity){
   state.contacts.geometry.dispose();
   state.contacts.geometry=new app.THREE.BufferGeometry();
   state.contacts.geometry.setAttribute('position',new app.THREE.Float32BufferAttribute(new Float32Array(contactCapacity*3),3).setUsage(app.THREE.DynamicDrawUsage));
  }
  if(state.path){app.scene.remove(state.path);state.path.geometry.dispose();state.path.material.dispose();}
  const {THREE}=app;
  state.path=new THREE.Line(new THREE.BufferGeometry().setFromPoints(state.trace.frames.map(frame=>new THREE.Vector3(...point(frame.qpos.slice(0,3))))),
   new THREE.LineBasicMaterial({color:'#ffd197',depthTest:false,transparent:true,opacity:.7}));
  state.path.renderOrder=2;app.scene.add(state.path);
  if(state.cameraHelper){app.scene.remove(state.cameraHelper);state.cameraHelper.dispose();}
  state.camera=recordedCamera(app);state.cameraHelper=new THREE.CameraHelper(state.camera);app.scene.add(state.cameraHelper);
  if(state.scale){app.scene.remove(state.scale);state.scale.geometry.dispose();state.scale.material.dispose();}
  const start=state.trace.frames[0].qpos.slice(0,3);start[1]-=.2;
  const end=[start[0]+.25,start[1],start[2]];
  state.scale=new THREE.Line(new THREE.BufferGeometry().setFromPoints([start,end].map(p=>new THREE.Vector3(...point(p)))),
   new THREE.LineBasicMaterial({color:'#ffffff',depthTest:false}));
  app.scene.add(state.scale);
  if(state.quality==='full')await makeFullGeometry(app);
  state.attachedVariant=getVariant();state.switching=false;view(state.view,{share:false});updateGeometry();warmup();
  $('motion-readiness').textContent=state.mediaError?`3D frames matched; a recording is unavailable: ${state.mediaError}. Use Reload recordings to retry.`:`Matched ${state.trace.frames.length} frames. White segment: 0.25 m; amber dots: recorded terrain contacts.`;
 }
 async function quality(value,{automatic=false}={}) {
  if(!['full','bounds','video'].includes(value))throw new Error('Unknown rendering detail');
  if(value!=='video'&&getApp()?.renderer.getContext().isContextLost()){
   $('motion-quality').value='video';
   $('motion-readiness').textContent='Reload the page to restore its lost graphics context. Recorded videos and frame data remain available.';
   return;
  }
  state.quality=value;$('motion-quality').value=value;warmup();
  const app=getApp();
  if(value==='video'){
   pause();
   if(app){app.renderer.domElement.hidden=true;app.renderer.setAnimationLoop(null);}
   $('poster').hidden=false;$('poster').src=`motion/${getVariant()}/poster.png`;$('overlay').hidden=true;
   await ensureTrace();
  }else if(app){
   app.renderer.setPixelRatio(value==='bounds'?1:Math.min(devicePixelRatio,2));
   app.resize();app.renderer.domElement.hidden=false;$('poster').hidden=true;
   await changeRepresentation(value==='bounds'?'collision':document.querySelector('input[name=representation]:checked').value);
   if(value==='full')await makeFullGeometry(app);
   app.renderer.setAnimationLoop(app.renderLoop);resize();updateGeometry();
  }
  if(!automatic)$('motion-readiness').textContent=value==='bounds'?'Body bounds are a simplified visual guide. Original poses and contact data are unchanged.':value==='video'?'Recorded videos and source-frame controls remain available without 3D.':'Showing the original robot meshes.';
 }
 function render(now) {
  const app=getApp();if(!app||!state.attached||state.quality==='video')return false;
  const renderer=app.renderer;
  if(!state.viewport)resize();
  const v=state.viewport;
  renderer.setScissorTest(false);renderer.clear();
  renderer.setViewport(v.x,v.y,v.width,v.height);renderer.setScissor(v.x,v.y,v.width,v.height);
  renderer.setScissorTest(true);renderer.render(app.scene,app.camera);renderer.setScissorTest(false);
  if(now>state.warmUntil&&state.lastRender&&now-state.lastRender<1000){
   state.samples.push(now-state.lastRender);
   const elapsed=state.samples.reduce((a,b)=>a+b,0);
   if(elapsed>=2500&&state.samples.length>=12){
    const sampleFrames=state.samples.length,measured=sampleFrames*1000/elapsed;state.renderFps=measured;
    $('performance-status').textContent=`Measured here: ${measured.toFixed(1)} render frames/s · ${state.quality==='bounds'?'body bounds':'robot meshes'} · pixel ratio ${renderer.getPixelRatio()}.`;
    state.samples=[];
    if($('automatic-detail').checked&&measured<(state.quality==='full'?18:12)){
     const next=state.quality==='full'?'bounds':'video';
     state.adaptations.push({from:state.quality,to:next,fps:measured,sample_frames:sampleFrames,elapsed_ms:elapsed});
     quality(next,{automatic:true}).then(()=>{
      $('motion-readiness').textContent=`Measured ${measured.toFixed(1)} render frames/s; switched to ${next==='bounds'?'body bounds and the collision proxy':'recordings only'}. Source frames and measurements are unchanged.`;
     }).catch(error);
    }
   }
  }
  state.lastRender=now;return true;
 }
 async function setVariant() {
  pause();selection++;state.switching=true;state.trace=null;mediaSources();labels();
  for(const object of [state.model,state.bounds,state.path,state.contacts,state.cameraHelper])if(object)object.visible=false;
  $('poster').src=`motion/${getVariant()}/poster.png`;
  if((!getApp()||state.quality==='video')&&cache.size){await ensureTrace();state.switching=false;}
 }
 async function graphicsUnavailable() {
  await quality('video');
  $('motion-readiness').textContent='3D is unavailable. Review the same recorded frames in the two videos or download their source data.';
 }
 function hashValues() {return {frame:String(state.frame),view:state.view,trace:record.cases[getVariant()].trace.sha256};}
 async function restoreView() {
  pause();restore();
  const supplied=new URLSearchParams(location.hash.slice(1)).get('trace');
  if(supplied&&supplied!==record.cases[getVariant()].trace.sha256){
   state.frame=0;
   $('motion-readiness').textContent='This link identifies a different trace. Showing this publication from frame 0; review its source hash before comparing.';
  }
  await setVariant();view(state.view,{share:false});seek(state.frame,{share:false});
 }
 $('motion-load').onclick=async()=>{try{pause();state.videosRequested=false;await ensureTrace();}catch(problem){error(problem);}};
 $('motion-play').onclick=()=>play().catch(error);
 $('motion-previous').onclick=()=>{pause();seek(state.frame-1);};
 $('motion-next').onclick=()=>{pause();seek(state.frame+1);};
 $('motion-end').onclick=()=>{pause();seek(total()-1);};
 $('motion-frame').oninput=()=>{const frame=Number($('motion-frame').value);pause();seek(frame);};
 $('camera-recorded').onclick=()=>view('recorded');
 $('camera-orbit').onclick=()=>view('orbit');
 $('motion-quality').onchange=()=>{
  $('automatic-detail').checked=false;
  quality($('motion-quality').value).catch(error);
 };
 for(const id of ['show-path','show-contacts','show-camera'])$(id).onchange=updateGeometry;
 $('motion-export').onclick=()=>{
  if(!state.trace)return;
  const result={schema:'robot-reel.scene-motion-frame.v1',case:getVariant(),source_trace:record.cases[getVariant()].trace,
   frame:state.trace.frames[state.frame],camera:state.trace.camera,blender_frame:state.frame+1,
   browser_view:state.view,world:state.trace.world};
  const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)+'\n'],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download=`scene-${getVariant()}-frame-${state.frame}.json`;link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
 };
 document.addEventListener('visibilitychange',()=>{warmup();if(document.hidden)pause();});
 const suppliedTrace=new URLSearchParams(location.hash.slice(1)).get('trace');
 if(suppliedTrace&&suppliedTrace!==record.cases[getVariant()].trace.sha256){
  state.frame=0;
  $('motion-readiness').textContent='This link identifies a different trace. Showing frame 0 from this publication; check the source hash before comparing.';
 }
 mediaSources();labels();writeHash();
 return {state,attach,setVariant,render,resize,graphicsUnavailable,hashValues,restoreView,
  seek,pause,quality,view,ensureTrace,warmup};
}
