/* Lazy-load pinned 3D libraries only after an explicit scene interaction. */
const $=id=>document.getElementById(id);
let variant='baseline',representation='mesh',app=null,loading=false,requestId=0,motion=null;
const descriptions={
 mesh:'The display mesh retains the scan’s texture coordinates after decimation. Metres are preserved; the browser uses Y-up coordinates. This is a recorded scene inspection, with no online simulation.',
 splats:'Spark renders 25,000 area-weighted, texture-sampled Gaussians derived from the mesh. These are surface samples, not a trained multi-view 3DGS reconstruction. Sparse regions and holes remain visible.',
 collision:'A 65 × 65 top-surface heightfield approximates the terrain. Missing scan samples become the base plane. This proxy does not reproduce overhangs or establish real-world contact accuracy.',
};
function update(){
 $('scene-title').textContent=`Coast Rocks 02 · ${variant==='baseline'?'original':'edited terrain ×1.4'}`;
 $('poster').src=motion?`motion/${variant}/poster.png`:`${variant}/preview.png`;
 $('caption').textContent=descriptions[representation];
 for(const [id,file] of [['glb','scene.glb'],['splats','terrain.splat'],['native-check','native-check.json']])$(id).href=`${variant}/${file}`;
 for(const key of ['variant','representation'])document.querySelectorAll(`input[name=${key}]`).forEach(el=>el.checked=el.value===(key==='variant'?variant:representation));
 writeHash();
}
function writeHash(){
 const hash=new URLSearchParams(location.hash.slice(1));
 hash.set('variant',variant);hash.set('representation',representation);
 if(motion)for(const [key,value] of Object.entries(motion.hashValues()))hash.set(key,value);
 try{history.replaceState(null,'',`#${hash}`);}catch{}
}
function restore(){
 const p=new URLSearchParams(location.hash.slice(1));
 if(['baseline','edited'].includes(p.get('variant')))variant=p.get('variant');
 if(Object.hasOwn(descriptions,p.get('representation')))representation=p.get('representation');
}
async function loadScene(){
 if(loading)return;
 loading=true;$('load').disabled=true;$('status').textContent='Loading the checked scene and 3D viewer…';
 try{
  await motionReady;
  if(!app){
   const [THREE,{OrbitControls},{GLTFLoader}]=await Promise.all([import('three'),import('three/addons/controls/OrbitControls.js'),import('three/addons/loaders/GLTFLoader.js')]);
   const renderer=new THREE.WebGLRenderer({antialias:false,alpha:false});
   renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.setClearColor('#09141e');
   renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.2;
   const canvas=renderer.domElement;canvas.tabIndex=0;canvas.setAttribute('aria-label','Interactive terrain. Drag to orbit, arrow keys to pan, scroll to zoom; reset camera button below.');
   const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(45,1,.05,500);
   const controls=new OrbitControls(camera,canvas);controls.enableDamping=true;controls.minDistance=8;controls.maxDistance=150;controls.maxPolarAngle=Math.PI*.49;
   controls.listenToKeyEvents(canvas);
   scene.add(new THREE.HemisphereLight('#d9f3ff','#49634d',2.4));
   const light=new THREE.DirectionalLight('#fff4d9',3);light.position.set(-20,40,15);scene.add(light);
   const grid=new THREE.GridHelper(60,12,'#3b665f','#19323c');grid.position.y=-.06;scene.add(grid);
   const resize=()=>{const {width,height}=$('stage').getBoundingClientRect();renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix();motion?.resize();};
   const reset=()=>{camera.position.set(35,26,35);controls.target.set(0,1.8,0);controls.update();};
   const renderLoop=now=>{if(document.hidden)return;if(controls.enabled)controls.update();if(!motion?.render(now))renderer.render(scene,camera);};
   app={THREE,scene,camera,renderer,controls,loader:new GLTFLoader(),cache:new Map(),reset,resize,renderLoop,spark:null};
   new ResizeObserver(resize).observe($('stage'));resize();reset();
   $('stage').append(canvas);$('poster').hidden=true;
   renderer.setAnimationLoop(renderLoop);
   canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();renderer.setAnimationLoop(null);$('status').textContent='The graphics context was lost. Reload to restore 3D; the render and downloads remain available.';$('poster').hidden=false;canvas.hidden=true;motion?.graphicsUnavailable().catch(error=>{$('status').textContent=error.message;});});
  }
  await show();
  $('overlay').hidden=true;
 }catch(error){
  $('status').textContent=`3D could not load: ${error.message}. The recorded render and downloads remain available.`;
  $('poster').hidden=false;if(app)app.renderer.domElement.hidden=true;
  $('overlay').hidden=false;
  if(motion)await motion.graphicsUnavailable().catch(()=>{});
 }finally{loading=false;$('load').disabled=false;}
}
async function show(){
 if(!app)return;
 const current=++requestId,key=variant,mode=representation;
 $('status').textContent=`Loading ${key} ${mode}…`;
 let objects=app.cache.get(key);
 if(!objects){
  const gltf=await app.loader.loadAsync(`${key}/scene.glb`);
  const mesh=gltf.scene.getObjectByName('ScanTerrain'),collision=gltf.scene.getObjectByName('CollisionHeightfield');
  if(!mesh||!collision)throw new Error('Both reviewed scene representations are required');
  collision.material=new app.THREE.MeshBasicMaterial({color:'#70edbe',wireframe:true});
  objects={root:gltf.scene,mesh,collision,splats:null};objects.root.visible=false;
  app.scene.add(objects.root);app.cache.set(key,objects);
 }
 if(mode==='splats'&&!objects.splats){
  const {SparkRenderer,SplatMesh}=await import('@sparkjsdev/spark');
  if(!app.spark){app.spark=new SparkRenderer({renderer:app.renderer});app.scene.add(app.spark);}
  const splats=new SplatMesh({url:`${key}/terrain.splat`});splats.visible=false;
  await splats.initialized;app.scene.add(splats);objects.splats=splats;
 }
 if(current!==requestId||key!==variant||mode!==representation)return;
 if(motion)await motion.attach(app);
 if(current!==requestId||key!==variant||mode!==representation)return;
 for(const [name,row] of app.cache){row.root.visible=name===key;row.mesh.visible=name===key&&mode==='mesh';row.collision.visible=name===key&&mode==='collision';if(row.splats)row.splats.visible=name===key&&mode==='splats';}
 const videoOnly=motion?.state.quality==='video';
 app.renderer.domElement.hidden=videoOnly;$('poster').hidden=!videoOnly;
 if(mode==='splats'&&!videoOnly){
  $('status').textContent='Preparing the first Gaussian frame…';
  const deadline=performance.now()+15000;
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  while(current===requestId&&(app.spark.sorting||app.spark.display.numSplats===0)){
   if(performance.now()>deadline)throw new Error('Gaussian rendering did not become ready');
   await new Promise(resolve=>requestAnimationFrame(resolve));
  }
  if(current!==requestId)return;
  // Present the sorted surface before announcing readiness to the user.
  app.renderer.render(app.scene,app.camera);
 }
 $('status').textContent=`Showing ${key==='baseline'?'original':'edited'} ${mode==='splats'?'surface Gaussians':mode==='collision'?'collision proxy':'textured mesh'}.`;
}
document.querySelectorAll('input[name=variant],input[name=representation]').forEach(el=>el.addEventListener('change',async()=>{
 if(el.name==='variant')variant=el.value;else representation=el.value;
 update();
 try{if(el.name==='variant')await motion?.setVariant();if(app&&motion?.state.quality!=='video')await show();}
 catch(error){$('status').textContent=`Could not change representation: ${error.message}`;}
}));
$('load').onclick=loadScene;
$('reset').onclick=()=>{if(app){if(motion)motion.view('scene');else app.reset();$('status').textContent='Whole scene view.';}else $('status').textContent='Open the 3D scene to use camera controls.';};
$('rotate').onclick=()=>{
 if(!app){$('status').textContent='Open the 3D scene to use the turntable.';return;}
 if(motion?.state.view==='recorded')motion.view('orbit');
 app.controls.autoRotate=!app.controls.autoRotate;
 $('rotate').setAttribute('aria-pressed',String(app.controls.autoRotate));
 $('rotate').textContent=app.controls.autoRotate?'Stop turntable':'Turntable';
};
$('share').onclick=async()=>{try{await navigator.clipboard.writeText(location.href);$('status').textContent='Copied this scene and representation.';}catch{$('status').textContent=`Copy the address from your browser to share this view: ${location.href}`;}};
$('recipe').onsubmit=event=>{
 event.preventDefault();if(!$('recipe').reportValidity())return;
 const values=new FormData($('recipe')),recipe={schema:'robot-reel.scene-edit.v1'};
 for(const key of ['terrain_z_scale','sun_azimuth_degrees','sun_energy'])recipe[key]=Number(values.get(key));
 const url=URL.createObjectURL(new Blob([JSON.stringify(recipe,null,2)+'\n'],{type:'application/json'}));
 const link=document.createElement('a');link.href=url;link.download='edit.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 $('status').textContent='Downloaded edit.json. Run the Blender recipe to generate and check the new scene.';
};
window.addEventListener('hashchange',async()=>{try{restore();if(motion)await motion.restoreView();update();if(app)await show();}catch(error){$('status').textContent=error.message;}});
const motionReady=fetch('manifest.json').then(response=>{
 if(!response.ok)throw new Error(`Scene manifest: HTTP ${response.status}`);
 return response.json();
}).then(async manifest=>{
 if(manifest.schema!=='robot-reel.scene-site.v2')return;
 const {mountMotion}=await import('./scene_motion_view.js');
 motion=await mountMotion({manifest,getVariant:()=>variant,getApp:()=>app,writeHash,
  changeRepresentation:async value=>{representation=value;update();if(app)await show();}});
 update();
}).catch(error=>{$('status').textContent=`Recorded motion is unavailable: ${error.message}. Terrain inspection and downloads remain available.`;});
restore();update();
