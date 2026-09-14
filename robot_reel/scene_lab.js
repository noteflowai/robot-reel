/* Lazy-load pinned 3D libraries only after an explicit scene interaction. */
const $=id=>document.getElementById(id);
let variant='baseline',representation='mesh',app=null,loading=false,requestId=0;
const descriptions={
 mesh:'The display mesh retains the scan’s texture coordinates after decimation. Metres are preserved; the browser uses Y-up coordinates. This is a recorded scene inspection, with no online simulation.',
 splats:'Spark renders 25,000 area-weighted, texture-sampled Gaussians derived from the mesh. These are surface samples, not a trained multi-view 3DGS reconstruction. Sparse regions and holes remain visible.',
 collision:'A 65 × 65 top-surface heightfield approximates the terrain. Missing scan samples become the base plane. This proxy does not reproduce overhangs or establish real-world contact accuracy.',
};
function update(){
 $('scene-title').textContent=`Coast Rocks 02 · ${variant==='baseline'?'original':'edited terrain ×1.4'}`;
 $('poster').src=`${variant}/preview.png`;
 $('caption').textContent=descriptions[representation];
 for(const [id,file] of [['glb','scene.glb'],['splats','terrain.splat'],['native-check','native-check.json']])$(id).href=`${variant}/${file}`;
 for(const key of ['variant','representation'])document.querySelectorAll(`input[name=${key}]`).forEach(el=>el.checked=el.value===(key==='variant'?variant:representation));
 const hash=new URLSearchParams({variant,representation});
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
   const resize=()=>{const {width,height}=$('stage').getBoundingClientRect();renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix();};
   const reset=()=>{camera.position.set(35,26,35);controls.target.set(0,1.8,0);controls.update();};
   app={THREE,scene,camera,renderer,controls,loader:new GLTFLoader(),cache:new Map(),reset,spark:null};
   new ResizeObserver(resize).observe($('stage'));resize();reset();
   $('stage').append(canvas);$('poster').hidden=true;
   renderer.setAnimationLoop(()=>{if(document.hidden)return;controls.update();renderer.render(scene,camera);});
   canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();$('status').textContent='The graphics context was lost. Reload to restore 3D; the render and downloads remain available.';$('poster').hidden=false;canvas.hidden=true;});
  }
  await show();
  $('overlay').hidden=true;
 }catch(error){
  $('status').textContent=`3D could not load: ${error.message}. The recorded render and downloads remain available.`;
  $('poster').hidden=false;if(app)app.renderer.domElement.hidden=true;
  $('overlay').hidden=false;
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
 if(current!==requestId)return;
 for(const [name,row] of app.cache){row.root.visible=name===key;row.mesh.visible=name===key&&mode==='mesh';row.collision.visible=name===key&&mode==='collision';if(row.splats)row.splats.visible=name===key&&mode==='splats';}
 app.renderer.domElement.hidden=false;$('poster').hidden=true;
 if(mode==='splats'){
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
document.querySelectorAll('input[name=variant],input[name=representation]').forEach(el=>el.addEventListener('change',()=>{
 if(el.name==='variant')variant=el.value;else representation=el.value;
 update();if(app)show().catch(error=>{$('status').textContent=`Could not change representation: ${error.message}`;});
}));
$('load').onclick=loadScene;
$('reset').onclick=()=>{if(app){app.reset();$('status').textContent='Camera reset.';}else $('status').textContent='Open the 3D scene to use camera controls.';};
$('rotate').onclick=()=>{
 if(!app){$('status').textContent='Open the 3D scene to use the turntable.';return;}
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
window.addEventListener('hashchange',()=>{restore();update();if(app)show().catch(error=>{$('status').textContent=error.message;});});
restore();update();
