// Exercise the actual scene, media frames and fallback; retain native-check input.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const fs=require('node:fs/promises');
const path=require('node:path');
const readline=require('node:readline');
const {chromium}=require('playwright');

async function main(){
 const root=path.resolve(process.argv[2]||'docs/scene-lab');
 const output=path.resolve(process.argv[3]||'artifacts/scene-motion-browser');
 await fs.mkdir(output,{recursive:true});
 const server=spawn('python3',['-u','-m','http.server','0','--bind','127.0.0.1','--directory',root],{stdio:['ignore','pipe','ignore']});
 const args=process.env.SCENE_BROWSER_GPU==='1'
  ?['--use-angle=vulkan','--enable-features=Vulkan','--disable-vulkan-surface']
  :['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'];
 let browser,page;
 try{
  const port=await new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>reject(new Error('HTTP server did not start')),10000);
   readline.createInterface({input:server.stdout}).on('line',line=>{
    const match=line.match(/port (\d+)/);if(match){clearTimeout(timer);resolve(Number(match[1]));}
   });
   server.once('error',reject);
  });
  const url=`http://127.0.0.1:${port}/`;
  browser=await chromium.launch({args});
  page=await browser.newPage({viewport:{width:1440,height:1100}});
  const errors=[],requests=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
  page.on('request',request=>requests.push(request.url()));
  await page.goto(url+'#variant=baseline&frame=1&view=recorded');
  await page.waitForFunction(()=>typeof motion!=='undefined'&&motion!==null);
  assert.equal(requests.some(value=>value.endsWith('.glb')||value.includes('/vendor/')),false);
  await page.locator('#automatic-detail').uncheck();
  await page.evaluate(()=>{
   window.presentedFrames={};
   for(const video of document.querySelectorAll('video')){
    const receive=(_now,meta)=>{window.presentedFrames[video.id]=meta.mediaTime;video.requestVideoFrameCallback(receive);};
    video.requestVideoFrameCallback(receive);
   }
  });
  await page.locator('#motion-load').click();
  await page.waitForFunction(()=>!document.getElementById('motion-play').disabled);
  assert.match(await page.locator('#motion-clock').textContent(),/0\.035 s/);
  assert.equal(requests.some(value=>value.endsWith('.glb')||value.includes('/vendor/')),false);
  await page.waitForFunction(()=>Object.keys(window.presentedFrames).length===2&&Object.values(window.presentedFrames).every(t=>Math.abs(t-1/30)<1e-5));
  await page.locator('#motion-frame').fill('90');
  await page.waitForFunction(()=>Object.keys(window.presentedFrames).length===2&&Object.values(window.presentedFrames).every(t=>Math.abs(t-3)<1e-5));
  await page.locator('#load').click();
  await page.waitForFunction(()=>document.getElementById('status').textContent.startsWith('Showing'),null,{timeout:60000});
  const readback={schema:'robot-reel.scene-browser-readback.v1',browser:{version:browser.version(),args},cases:{}};
  readback.browser.renderer=await page.evaluate(()=>{
   const gl=app.renderer.getContext(),ext=gl.getExtension('WEBGL_debug_renderer_info');
   return ext?gl.getParameter(ext.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER);
  });
  for(const variant of ['baseline','edited']){
   await page.locator(`input[name=variant][value=${variant}]`).check();
   await page.waitForFunction(value=>motion.state.trace?.case===value&&motion.state.bodyNodes.length===15&&document.getElementById('status').textContent.startsWith(`Showing ${value==='baseline'?'original':'edited'}`),variant,{timeout:60000});
   await page.locator('#camera-recorded').click();
   readback.cases[variant]=await page.evaluate(async()=>{
    motion.pause();
    const meshes=[];motion.state.model.traverse(node=>{if(node.isMesh)meshes.push(node);});
    meshes.sort((a,b)=>a.name.localeCompare(b.name));
    const frames=[];
    for(let i=0;i<motion.state.trace.frames.length;i++){
     motion.seek(i,{share:false});app.scene.updateMatrixWorld(true);app.camera.updateMatrixWorld(true);
     const camera=app.camera,source=motion.state.trace.camera;
     const projections=motion.state.bodyNodes.map(node=>{
      const position=node.getWorldPosition(new app.THREE.Vector3());
      const depth=-position.clone().applyMatrix4(camera.matrixWorldInverse).z;
      position.project(camera);
      return [(position.x+1)*source.width/2,(1-position.y)*source.height/2,depth];
     });
     const contacts=motion.state.contacts.geometry,attribute=contacts.getAttribute('position');
     frames.push({frame:motion.state.frame,bodies:motion.state.bodyNodes.map(node=>node.matrixWorld.elements.slice()),
      visuals:meshes.map(node=>node.matrixWorld.elements.slice()),camera:camera.matrixWorld.elements.slice(),
      projections,contacts:Array.from({length:contacts.drawRange.count},(_,i)=>[attribute.getX(i),attribute.getY(i),attribute.getZ(i)])});
    }
    const hash=async array=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',array.buffer.slice(array.byteOffset,array.byteOffset+array.byteLength))),b=>b.toString(16).padStart(2,'0')).join('');
    const geometry=await Promise.all(meshes.map(async node=>({
     name:node.name,vertices:node.geometry.attributes.position.count,indices:node.geometry.index.count,
     positions_sha256:await hash(node.geometry.attributes.position.array),indices_sha256:await hash(node.geometry.index.array),
    })));
    return {source_trace:motion.state.record.cases[motion.state.variant].trace,
     body_names:motion.state.trace.bodies,visual_names:meshes.map(node=>node.name),geometry,frames};
   });
   await fs.writeFile(path.join(output,'readback.json'),JSON.stringify(readback)+'\n');
   await page.locator('#motion-frame').fill('90');
   await page.waitForFunction(()=>Object.values(window.presentedFrames).every(t=>Math.abs(t-3)<1e-5));
   await page.screenshot({path:path.join(output,`${variant}-recorded-camera.png`),fullPage:true});
  }
  await fs.writeFile(path.join(output,'readback.json'),JSON.stringify(readback)+'\n');
  await page.locator('#camera-orbit').click();
  assert.equal(await page.evaluate(()=>app.controls.enabled),true);
  assert.equal(await page.evaluate(()=>motion.state.cameraHelper.visible),true);
  await page.locator('input[name=representation][value=splats]').check();
  await page.waitForFunction(()=>document.getElementById('status').textContent.includes('surface Gaussians'),null,{timeout:60000});
  assert.equal(await page.evaluate(()=>app.cache.get('edited').splats.splats.getNumSplats()),25000);
  assert.ok(await page.evaluate(()=>app.spark.display.numSplats)>0);
  await page.screenshot({path:path.join(output,'edited-splats-orbit.png'),fullPage:true});
  await page.locator('input[name=representation][value=mesh]').check();
  await page.waitForFunction(()=>document.getElementById('status').textContent.includes('textured mesh'));
  await page.locator('#motion-frame').fill('43');
  const download=page.waitForEvent('download');await page.locator('#motion-export').click();
  const selected=JSON.parse(await fs.readFile(await (await download).path(),'utf8'));
  await fs.writeFile(path.join(output,'selected-frame.json'),JSON.stringify(selected,null,2)+'\n');
  const trace=JSON.parse(await fs.readFile(path.join(root,'motion/edited/trace.json'),'utf8'));
  assert.deepEqual(selected.frame,trace.frames[43]);assert.deepEqual(selected.camera,trace.camera);
  assert.equal(selected.blender_frame,44);
  await page.locator('#motion-simulation').evaluate(video=>video.play());
  await page.waitForFunction(()=>document.getElementById('motion-simulation').currentTime>1.6);
  assert.equal(await page.evaluate(()=>motion.state.playing),false);
  await page.locator('#motion-next').click();
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('video')).every(video=>video.paused&&!video.seeking&&Math.abs(video.currentTime-(44.25/30))<.003));
  const shared=page.url();await page.reload();
  await page.waitForFunction(()=>typeof motion!=='undefined'&&motion!==null);
  assert.equal(await page.locator('#motion-frame').inputValue(),'44');
  assert.equal(await page.locator('input[name=variant][value=edited]').isChecked(),true);
  await page.locator('#load').click();
  await page.waitForFunction(()=>document.getElementById('status').textContent.startsWith('Showing'),null,{timeout:60000});
  await page.locator('#automatic-detail').uncheck();
  for(const width of [390,320]){
   await page.setViewportSize({width,height:1000});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   await page.locator('#motion-frame').focus();await page.keyboard.press('ArrowRight');
   await page.screenshot({path:path.join(output,`scene-${width}.png`),fullPage:true});
  }
  assert.equal(await page.evaluate(()=>motion.state.frame),46);
  // Measured delay is deliberately injected to test the fallback policy. It is
  // excluded from device benchmarks, which run separately without this load.
  const slow=async()=>page.evaluate(()=>{
   document.getElementById('automatic-detail').checked=true;
   motion.state.warmUntil=0;motion.state.samples=[];motion.state.lastRender=0;
   app.renderer.setAnimationLoop(now=>{const start=performance.now();while(performance.now()-start<120){}app.renderLoop(now);});
  });
  await slow();
  await page.waitForFunction(()=>motion.state.quality==='bounds',null,{timeout:20000});
  await page.waitForFunction(()=>app.cache.get('edited').collision.visible);
  await slow();
  await page.waitForFunction(()=>motion.state.quality==='video',null,{timeout:20000});
  const adaptations=await page.evaluate(()=>motion.state.adaptations);
  assert.deepEqual(adaptations.map(value=>value.to),['bounds','video']);
  await page.locator('#motion-next').click();
  assert.equal(await page.evaluate(()=>motion.state.frame),47);
  await page.locator('input[name=variant][value=baseline]').check();
  await page.waitForFunction(()=>motion.state.trace?.case==='baseline');
  await page.locator('#motion-quality').selectOption('full');
  await page.waitForFunction(()=>motion.state.quality==='full'&&!app.renderer.domElement.hidden&&motion.state.attachedVariant==='baseline');
  await page.evaluate(()=>app.renderer.getContext().getExtension('WEBGL_lose_context').loseContext());
  await page.waitForFunction(()=>motion.state.quality==='video'&&document.getElementById('motion-readiness').textContent.includes('3D is unavailable'));
  await page.locator('#motion-next').click();
  assert.equal(await page.evaluate(()=>motion.state.frame),48);
  for(const width of [390,320]){
   const mobile=await browser.newPage({viewport:{width,height:900}});
   await mobile.goto(url);
   await mobile.waitForFunction(()=>typeof motion!=='undefined'&&motion!==null);
   assert.equal(await mobile.locator('.motion-details').evaluate(node=>node.open),false);
   assert.equal(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   await mobile.screenshot({path:path.join(output,`initial-${width}.png`),fullPage:true});
   await mobile.close();
  }
  const noGraphics=await browser.newPage({viewport:{width:1440,height:1000}});
  await noGraphics.addInitScript(()=>{
   const original=HTMLCanvasElement.prototype.getContext;
   HTMLCanvasElement.prototype.getContext=function(kind,...args){
    if(kind==='webgl'||kind==='webgl2'||kind==='experimental-webgl')return null;
    return original.call(this,kind,...args);
   };
  });
  await noGraphics.goto(url);
  await noGraphics.waitForFunction(()=>typeof motion!=='undefined'&&motion!==null);
  await noGraphics.locator('#load').click();
  await noGraphics.waitForFunction(()=>motion.state.quality==='video'&&!document.getElementById('motion-next').disabled);
  await noGraphics.locator('#motion-next').click();
  assert.equal(await noGraphics.evaluate(()=>motion.state.frame),1);
  await noGraphics.screenshot({path:path.join(output,'without-webgl.png'),fullPage:true});
  await noGraphics.close();
  assert.deepEqual(errors,[]);
  const checks={passed:true,source_cases:2,source_frames:362,shared,viewport_widths:[1440,390,320],
   actual_video_frames_checked:[1,90],keyboard_frames:true,independent_video_playback:true,
   scripted_slow_frame_load_ms:120,adaptations,context_loss_fallback:true,
   initial_graphics_failure_fallback:true,initial_mobile_details_collapsed:true,
   video_case_switch_and_return_to_3d:true,errors};
  await fs.writeFile(path.join(output,'checks.json'),JSON.stringify(checks,null,2)+'\n');
  console.log(JSON.stringify(checks));
 }catch(error){
  if(page){
   await page.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});
   const state=await page.evaluate(()=>({
    status:document.getElementById('status').textContent,
    readiness:document.getElementById('motion-readiness').textContent,
    frame:typeof motion!=='undefined'?motion?.state.frame:null,
    presented:window.presentedFrames,
    videos:Array.from(document.querySelectorAll('video')).map(v=>({id:v.id,time:v.currentTime,duration:v.duration,src:v.currentSrc,network:v.networkState,seekable:Array.from({length:v.seekable.length},(_,i)=>[v.seekable.start(i),v.seekable.end(i)]),seeking:v.seeking,ready:v.readyState,paused:v.paused,error:v.error?.message})),
   })).catch(()=>null);
   await fs.writeFile(path.join(output,'failure.json'),JSON.stringify({error:error.message,state},null,2)+'\n');
  }
  throw error;
 }finally{await browser?.close();server.kill('SIGTERM');}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
