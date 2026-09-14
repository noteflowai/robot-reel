const {test, before, after} = require('node:test');
const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const {readFile, writeFile, mkdtemp, rm} = require('node:fs/promises');
const {existsSync} = require('node:fs');
const {tmpdir} = require('node:os');
const {join, resolve, extname} = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require('playwright');
const {spawnSync} = require('node:child_process');
const {createHash} = require('node:crypto');
let browser, server, base;
test('Microduck pause synchronizes telemetry when animation frames were throttled',async()=>{
 const page=await browser.newPage();
 try{
  await page.addInitScript(()=>{window.requestAnimationFrame=()=>0;});
  await page.goto(base+'/microduck-lab/#run=right&frame=120&joint=3');
  await page.waitForFunction(()=>{const v=document.querySelector('video');return v.readyState>=2&&!v.seeking;},null,{polling:50});
  await page.locator('#play').click();
  await page.waitForFunction(()=>document.querySelector('video').currentTime>4.3,null,{polling:50});
  assert.equal(await page.locator('#counter').textContent(),'Frame 120 / 299');
  await page.locator('#play').click();
  const state=await page.evaluate(()=>({paused:document.querySelector('video').paused,
   clock:Math.floor(document.querySelector('video').currentTime*30+1e-5),
   frame:Number(document.querySelector('#counter').textContent.match(/\d+/)[0])}));
  assert.equal(state.paused,true);assert.equal(state.frame,state.clock);assert.ok(state.frame>120);
 }finally{await page.close();}
});
test('Microduck motion links original angles, clocks and videos at desktop/mobile widths, online and offline',async()=>{
  const source=JSON.parse(await readFile('docs/microduck-lab/right-trace.json','utf8'));
  const left=JSON.parse(await readFile('docs/microduck-lab/left-trace.json','utf8'));
  for(const width of [1440,390]){
    const page=await browser.newPage({viewport:{width,height:1050},reducedMotion:'reduce'}),errors=[],external=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.route(/^https?:/,route=>route.request().url().startsWith(base)?route.continue():(external.push(route.request().url()),route.abort()));
    try{
      const target=width===390?pathToFileURL(resolve('docs/microduck-lab/index.html')).href:base+'/microduck-lab/';
      await page.goto(target+'#run=right&frame=120&joint=3');
      await page.waitForFunction(()=>{const v=document.querySelector('video');return v.readyState>=2&&!v.seeking;});
      assert.equal(await page.locator('#counter').textContent(),'Frame 120 / 299');
      assert.equal(await page.locator('#measured').textContent(),source.frames[120].qpos[3].toFixed(3));
      assert.equal(await page.locator('#target').textContent(),source.frames[120].target[3].toFixed(3));
      assert.equal(await page.locator('#sample-time').textContent(),source.frames[120].sim_time.toFixed(3)+' s');
      assert.equal(await page.locator('video').evaluate(v=>Math.floor(v.currentTime*30)),120);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      const image=await page.locator('#scene').evaluate(c=>c.toDataURL());
      await page.locator('#orbit-left').click();
      assert.notEqual(await page.locator('#scene').evaluate(c=>c.toDataURL()),image);
      await page.locator('#ghost').click();assert.equal(await page.locator('#ghost').getAttribute('aria-pressed'),'false');
      await page.locator('#share').click();const url=await page.locator('#share-url').inputValue();
      const expectedImage=await page.locator('#scene').evaluate(c=>c.toDataURL());
      await page.goto(url);
      assert.equal(await page.locator('#scene').evaluate(c=>c.toDataURL()),expectedImage);
      const pending=page.waitForEvent('download');await page.locator('#sample-json').click();
      const sample=JSON.parse(await readFile(await (await pending).path(),'utf8'));
      assert.equal(sample.trace_sha256,createHash('sha256').update(await readFile('docs/microduck-lab/right-trace.json')).digest('hex'));
      assert.equal(sample.measured_rad,source.frames[120].qpos[3]);
      assert.equal(sample.target_rad,source.frames[120].target[3]);
      assert.equal(sample.policy_step,source.frames[120].policy_step);
      await page.locator('#run').selectOption('left');
      await page.waitForFunction(()=>{const v=document.querySelector('video');return v.readyState>=2&&!v.seeking&&v.currentSrc.endsWith('left.mp4');});
      assert.equal(await page.locator('#counter').textContent(),'Frame 120 / 299');
      assert.equal(await page.locator('#measured').textContent(),left.frames[120].qpos[3].toFixed(3));
      const csvPending=page.waitForEvent('download');await page.locator('#csv').click();
      const csv=(await readFile(await (await csvPending).path(),'utf8')).trim().split('\n');
      assert.equal(csv.length,4201);
      const row=csv[120*14+3+1].split(',');
      assert.equal(row[5],'left_knee');assert.equal(Number(row[6]),left.frames[120].qpos[3]);
      let peak={error:-1,frame:0,joint:0};
      left.frames.forEach(f=>f.qpos.forEach((q,j)=>{const error=Math.abs(q-f.target[j]);if(error>peak.error)peak={error,frame:f.frame,joint:j};}));
      await page.locator('#peak').click();
      assert.equal(await page.locator('#counter').textContent(),`Frame ${peak.frame} / 299`);
      assert.equal(await page.locator('#joint').inputValue(),String(peak.joint));
      const map=await page.locator('#heatmap').boundingBox(),offset=map.width<500?111:137;
      await page.locator('#heatmap').click({position:{x:offset+(map.width-offset-12)*.505,y:12+2.5*(map.height-35)/14}});
      assert.equal(await page.locator('#joint').inputValue(),'2');
      const clicked=Number((await page.locator('#counter').textContent()).match(/\d+/)[0]);
      // On mobile a heatmap pixel covers more than one video frame.
      assert.ok(clicked>=150&&clicked<=152);
      await page.locator('#next').click();
      assert.equal(await page.locator('#counter').textContent(),`Frame ${clicked+1} / 299`);
      await page.locator('#play').click();
      await page.waitForFunction(previous=>document.querySelector('#counter').textContent!==previous,`Frame ${clicked+1} / 299`);
      await page.locator('#play').click();
      const clock=await page.locator('video').evaluate(v=>Math.floor(v.currentTime*30+1e-5));
      assert.ok(Math.abs(Number((await page.locator('#counter').textContent()).match(/\d+/)[0])-clock)<=1);
      assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
    }finally{await page.close();}
  }
});
test('Microduck invalid view parameters and absent video preserve inspectable source telemetry',async()=>{
 const page=await browser.newPage({viewport:{width:390,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.route('**/microduck-lab/*.mp4',route=>route.abort());
  await page.goto(base+'/microduck-lab/#frame=NaN&joint=-1&yaw=Infinity&pitch=2&run=unknown');
  assert.equal(await page.locator('#counter').textContent(),'Frame 120 / 299');
  assert.equal(await page.locator('#joint').inputValue(),'3');
  await page.waitForFunction(()=>document.querySelector('#video-status').textContent.startsWith('Video unavailable'));
  assert(await page.locator('#play').isDisabled());
  await page.locator('#next').click();
  assert.equal(await page.locator('#counter').textContent(),'Frame 121 / 299');
  await page.unroute('**/microduck-lab/*.mp4');
  await page.locator('#retry-video').click();
  await page.waitForFunction(()=>{const v=document.querySelector('video');return v.readyState>=2&&!v.seeking;});
  assert.equal(await page.locator('video').evaluate(v=>Math.floor(v.currentTime*30)),121);
  assert(await page.locator('#retry-video').isHidden());
  assert(await page.locator('#play').isEnabled());
  assert.equal(await page.evaluate(()=>document.activeElement.id),'recording');
  assert.deepEqual(errors,[]);
 }finally{await page.close();}
});
test('Microduck keyboard orbit, frame boundaries and stale playback recovery preserve the current view',async()=>{
 const page=await browser.newPage({viewport:{width:390,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(base+'/microduck-lab/#run=right&frame=61&joint=3');
  await page.waitForFunction(()=>document.querySelector('video').readyState>=2);
  const initialPitch=await page.evaluate(()=>pitch);
  await page.locator('#orbit-up').focus();await page.keyboard.press('Enter');
  assert.ok(await page.evaluate(()=>pitch)>initialPitch);
  await page.locator('#orbit-down').focus();await page.keyboard.press('Enter');
  assert.ok(Math.abs(await page.evaluate(()=>pitch)-initialPitch)<1e-12);
  await page.locator('#timeline').focus();await page.keyboard.press('Home');
  assert(await page.locator('#previous').isDisabled());
  assert.match(await page.locator('#timeline').getAttribute('aria-valuetext'),/^Frame 0 of 299/);
  await page.keyboard.press('End');assert(await page.locator('#next').isDisabled());
  await page.evaluate(()=>{HTMLMediaElement.prototype.play=function(){return new Promise((resolve,reject)=>{window.rejectOldPlay=()=>reject(Error('old media request'));});};});
  await page.locator('#play').click();
  await page.locator('#run').selectOption('left');
  await page.waitForFunction(()=>{const v=document.querySelector('video');return v.currentSrc.endsWith('left.mp4')&&v.readyState>=2&&!v.seeking;});
  await page.evaluate(async()=>{window.rejectOldPlay();await Promise.resolve();});
  assert.equal(await page.locator('#play').textContent(),'Play recording');
  assert.equal(await page.locator('#play').getAttribute('aria-busy'),'false');
  assert.match(await page.locator('#video-status').textContent(),/^Recording ready/);
  await page.evaluate(()=>{URL.createObjectURL=()=>{throw Error('download denied');};});
  await page.locator('#sample-json').click();
  assert.match(await page.locator('#status').textContent(),/^Download could not start/);
  assert.equal(await page.locator('#run').inputValue(),'left');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(errors,[]);
 }finally{await page.close();}
});
test('Microduck tap selection, orbit and verified frame exchange work online and offline',async()=>{
 const trace=JSON.parse(await readFile('docs/microduck-lab/left-trace.json','utf8'));
 for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:1050},hasTouch:width===390}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  try{
   await page.goto((width===390?pathToFileURL(resolve('docs/microduck-lab/index.html')).href:base+'/microduck-lab/')+'#run=left&frame=61&joint=3');
   await page.locator('#scene').scrollIntoViewIfNeeded();
   // Hit an isolated, actually rendered joint. Its readout must match the raw trace.
   const point=await page.evaluate(()=>jointPoints.find(p=>p.joint!==3&&jointPoints.every(q=>q===p||Math.hypot(q.x-p.x,q.y-p.y)>24)));
   assert.ok(point);
   const box=await page.locator('#scene').boundingBox();
   if(width===390)await page.touchscreen.tap(box.x+point.x,box.y+point.y);
   else await page.mouse.click(box.x+point.x,box.y+point.y);
   assert.equal(await page.locator('#joint').inputValue(),String(point.joint));
   assert.equal(await page.locator('#measured').textContent(),trace.frames[61].qpos[point.joint].toFixed(3));
   const before=await page.locator('#scene').evaluate(c=>c.toDataURL());
   await page.mouse.move(box.x+point.x,box.y+point.y);await page.mouse.down();
   await page.mouse.move(box.x+point.x+50,box.y+point.y+20,{steps:5});await page.mouse.up();
   assert.equal(await page.locator('#joint').inputValue(),String(point.joint));
   assert.notEqual(await page.locator('#scene').evaluate(c=>c.toDataURL()),before);
   await page.mouse.click(box.x+8,box.y+8);
   assert.equal(await page.locator('#joint').inputValue(),String(point.joint));
   const pending=page.waitForEvent('download');await page.locator('#sample-json').click();
   const file=await (await pending).path(),bytes=await readFile(file),record=JSON.parse(bytes);
   // The independent Python verifier consumes the actual browser download.
   const checked=spawnSync('python3',['scripts/build_microduck_lab.py','--verify','--frame-json',file],{encoding:'utf8'});
   assert.equal(checked.status,0,checked.stderr);
   assert.equal(JSON.parse(checked.stdout).frame.joint,trace.joints[point.joint]);
   await page.locator('#run').selectOption('right');await page.locator('#next').click();
   await page.locator('#joint').selectOption('9');await page.locator('#orbit-right').click();
   const orbit=await page.evaluate(()=>({yaw,pitch,ghost}));
   await page.locator('#frame-file').setInputFiles({name:'shared.json',mimeType:'application/json',buffer:bytes});
   await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Verified frame 61'));
   assert.equal(await page.locator('#run').inputValue(),'left');
   assert.equal(await page.locator('#joint').inputValue(),String(point.joint));
   assert.equal(await page.locator('#counter').textContent(),'Frame 61 / 299');
   assert.deepEqual(await page.evaluate(()=>({yaw,pitch,ghost})),orbit);
   await page.waitForFunction(()=>{const v=document.querySelector('video');return v.readyState>=2&&!v.seeking&&v.currentSrc.endsWith('left.mp4');});
   assert.equal(await page.locator('video').evaluate(v=>Math.floor(v.currentTime*30)),61);
   const state=await page.evaluate(()=>({runIndex,frame,joint,yaw,pitch,ghost,hash:location.hash}));
   for(const bad of [
    {...record,measured_rad:record.measured_rad+.001},{...record,trace_sha256:'0'.repeat(64)},
    {...record,frame:true},{...record,extra:1},{...record,model_commit:'0'.repeat(40)},
    {...record,scope:{}},{...record,frame:300},{...record,schema:'unknown'},
    bytes.toString().trim().slice(0,-1)+',"fr\\u0061me":61}',
    '['.repeat(33)+']'.repeat(33),Buffer.from([0xff]),' '.repeat(16385),
   ]){
    const buffer=Buffer.isBuffer(bad)?bad:Buffer.from(typeof bad==='string'?bad:JSON.stringify(bad));
    await page.locator('#frame-file').setInputFiles({name:'invalid.json',mimeType:'application/json',buffer});
    await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Could not open frame:'));
    assert.deepEqual(await page.evaluate(()=>({runIndex,frame,joint,yaw,pitch,ghost,hash:location.hash})),state);
   }
   // A slower earlier selection cannot overwrite a newer file choice.
   await page.evaluate(()=>{const original=File.prototype.arrayBuffer;window.releaseFrameRead=null;let first=true;File.prototype.arrayBuffer=function(){if(first){first=false;return new Promise(resolve=>{window.releaseFrameRead=()=>original.call(this).then(resolve);});}return original.call(this);};});
   await page.locator('#frame-file').setInputFiles({name:'slow.json',mimeType:'application/json',buffer:bytes});
   await page.locator('#run').selectOption('right');
   const newer=page.waitForEvent('download');await page.locator('#sample-json').click();
   await page.locator('#frame-file').setInputFiles({name:'newer.json',mimeType:'application/json',buffer:await readFile(await (await newer).path())});
   await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Verified frame 61'));
   await page.evaluate(async()=>{await window.releaseFrameRead();await new Promise(resolve=>setTimeout(resolve,0));});
   assert.equal(await page.locator('#run').inputValue(),'right');
   assert.deepEqual(errors,[]);
  }finally{await page.close();}
 }
});
before(async()=>{
  server = createServer(async(req,res)=>{
    const path = new URL(req.url, 'http://localhost').pathname;
    const file = resolve('docs', '.'+(path.endsWith('/')?path+'index.html':path));
    if(!file.startsWith(resolve('docs')+'/')){res.writeHead(403).end();return;}
    try {
      const data=await readFile(file);
      const mime={'.html':'text/html','.mp4':'video/mp4','.png':'image/png'};
      const headers={'Content-Type':mime[extname(file)]||'application/octet-stream','Accept-Ranges':'bytes'};
      const range=/^bytes=(\d+)-(\d*)$/.exec(req.headers.range||'');
      if(range){
        const start=Number(range[1]),end=Math.min(data.length-1,range[2]?Number(range[2]):data.length-1);
        if(start>end){res.writeHead(416,{'Content-Range':`bytes */${data.length}`}).end();return;}
        res.writeHead(206,{...headers,'Content-Length':end-start+1,'Content-Range':`bytes ${start}-${end}/${data.length}`});
        res.end(data.subarray(start,end+1));
      }else{res.writeHead(200,{...headers,'Content-Length':data.length});res.end(data);}
    }catch{res.writeHead(404).end();}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  base=`http://127.0.0.1:${server.address().port}`;
  browser=await chromium.launch();
});
after(async()=>{await browser?.close();await new Promise(resolve=>server?.close(resolve));});
async function stressExample(shortReference=false){
  const html=await readFile('docs/stress/index.html','utf8');
  const data=JSON.parse(html.split('<script id="stress-data" type="application/json">')[1].split('</script>')[0]);
  const candidates=data.summary.pairs.map(p=>({
    ...p,
    reference:data.traces.find(t=>t.seed===p.seed&&t.stress.condition==='reference'),
    other:data.traces.find(t=>t.seed===p.seed&&t.stress.condition===p.condition),
  }));
  const pair=candidates.find(p=>shortReference
    ?p.reference.result.actions<p.other.result.actions
    :p.reference.result.actions>p.other.result.actions)
    ||candidates.find(p=>p.reference.result.actions!==p.other.result.actions)||candidates[0];
  return {data,...pair,max:Math.max(pair.reference.result.actions,pair.other.result.actions),
    shorter:pair.reference.result.actions<pair.other.result.actions?'left':'right'};
}
test('Cloth Lab compares original binary vertices and preserves their clock through overlay and sharing',async()=>{
  const page=await browser.newPage({viewport:{width:1440,height:1100},reducedMotion:'reduce'});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  try{
    const trace=JSON.parse(await readFile('docs/cloth/trace.json','utf8'));
    const q=await readFile('docs/cloth/positions.f32');
    const vertex=(f,c,i)=>Array.from({length:3},(_,axis)=>q.readFloatLE(4*(((f*3+c)*117+i)*3+axis)));
    const rms=(f,c)=>Math.sqrt(Array.from({length:117},(_,i)=>{
      const p=vertex(f,c,i),reference=vertex(f,0,i);
      return p.reduce((sum,v,k)=>sum+(v-reference[k])**2,0);
    }).reduce((a,b)=>a+b,0)/117);
    await page.goto(base+'/cloth/#frame=61&case=1&view=separate');
    assert.equal(await page.locator('#counter').textContent(),'Sample 61 / 120');
    assert.equal(await page.locator('#distance').textContent(),rms(61,1).toFixed(3));
    assert.equal(await page.locator('#time').textContent(),(61/30).toFixed(3));
    assert.equal(await page.locator('#dcc-frame').textContent(),'Blender frame 62');
    const dropped=1.5-trace.free_edge_vertices.reduce((sum,i)=>sum+vertex(61,1,i)[2],0)/9;
    assert.equal(await page.locator('#drop').textContent(),dropped.toFixed(3)+' m');
    const image=await page.locator('#scene').evaluate(c=>c.toDataURL());
    await page.locator('#rotate-left').click();
    assert.notEqual(await page.locator('#scene').evaluate(c=>c.toDataURL()),image);
    await page.locator('#overlay').click();
    assert.equal(await page.locator('#distance').textContent(),rms(61,1).toFixed(3));
    const sharedImage=await page.locator('#scene').evaluate(c=>c.toDataURL());
    await page.locator('#share').click();await page.reload();
    assert.equal(await page.locator('#scene').evaluate(c=>c.toDataURL()),sharedImage);
    assert.equal(await page.locator('#counter').textContent(),'Sample 61 / 120');
    assert.equal(await page.locator('#overlay').getAttribute('aria-pressed'),'true');
    assert.equal(await page.getByRole('button',{name:'Bending coefficient 1',exact:true}).getAttribute('aria-pressed'),'true');
    await page.locator('#next').click();
    assert.equal(await page.locator('#counter').textContent(),'Sample 62 / 120');
    assert.equal(await page.locator('#distance').textContent(),rms(62,1).toFixed(3));
    await page.locator('#peak').click();
    assert.equal(await page.locator('#distance').textContent(),trace.summary.peak.rms_m.toFixed(3));
    assert.equal(await page.locator('#counter').textContent(),`Sample ${trace.summary.peak.frame} / 120`);
    const downloaded=page.waitForEvent('download');
    await page.locator('#download-archive').click();
    assert.deepEqual(await readFile(await (await downloaded).path()),await readFile('docs/cloth/experiment.zip'));
    assert.deepEqual(errors,[]);
  }finally{await page.close();}
});
test('Cloth figures and sample records carry binary-derived facts and restore the same camera offline',async()=>{
  const trace=JSON.parse(await readFile('docs/cloth/trace.json','utf8')),q=await readFile('docs/cloth/positions.f32');
  const vertex=(f,c,i,axis)=>q.readFloatLE(4*(((f*3+c)*117+i)*3+axis));
  const rms=Math.sqrt(Array.from({length:117},(_,i)=>[0,1,2].reduce((sum,a)=>sum+(vertex(61,1,i,a)-vertex(61,0,i,a))**2,0)).reduce((a,b)=>a+b,0)/117);
  const drop=1.5-trace.free_edge_vertices.reduce((sum,i)=>sum+vertex(61,1,i,2),0)/9;
  const fingerprint=createHash('sha256').update(q).digest('hex');
  for(const width of [1440,390]){
    const page=await browser.newPage({viewport:{width,height:1100},reducedMotion:'reduce'}),errors=[],requests=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.route(/^https?:/,route=>{requests.push(route.request().url());return route.abort();});
    try{
      const url=pathToFileURL(resolve('docs/cloth/index.html')).href;
      await page.goto(url+'#frame=61&case=1&view=overlay');
      await page.locator('#rotate-left').click();
      const download=async id=>{const pending=page.waitForEvent('download');await page.locator(id).click();const file=await pending;return {name:file.suggestedFilename(),bytes:await readFile(await file.path())};};
      const recordFile=await download('#sample-json'),record=JSON.parse(recordFile.bytes);
      assert.equal(recordFile.name,'robot-reel-cloth-bend_1-sample-061.json');
      assert.equal(record.schema,'robot-reel-cloth-sample-1');
      assert.equal(record.sample,61);assert.equal(record.time_s,61/30);assert.equal(record.blender_frame,62);
      assert.deepEqual(record.case,{index:1,id:'bend_1',edge_ke:1});
      assert.deepEqual(record.reference,{index:0,id:'bend_001',edge_ke:.01});
      assert.ok(Math.abs(record.metrics.rms_separation_m-rms)<1e-12);
      assert.ok(Math.abs(record.metrics.mean_free_edge_drop_m-drop)<1e-12);
      assert.equal(record.metrics.max_pin_displacement_m,0);
      assert.equal(record.source.positions_sha256,fingerprint);
      for(const [key,value] of Object.entries(trace.source))assert.deepEqual(record.source[key],value);
      assert.deepEqual(record.presentation.display_offsets_x_m,[0,0,0]);
      assert.equal(record.presentation.mode,'overlay');
      assert.ok(Math.abs(record.presentation.yaw_rad+.68)<1e-12);
      assert.equal(record.presentation.pitch_rad,.65);
      assert.ok(!recordFile.bytes.includes(Buffer.from('file:')));
      await page.evaluate(()=>{
        window.figureText=[];
        const original=CanvasRenderingContext2D.prototype.fillText;
        CanvasRenderingContext2D.prototype.fillText=function(text,...args){if(this.canvas.width===1920)window.figureText.push(text);return original.call(this,text,...args);};
      });
      const png=await download('#figure');
      assert.equal(png.name,'robot-reel-cloth-bend_1-sample-061.png');
      assert.deepEqual([...png.bytes.subarray(0,8)],[137,80,78,71,13,10,26,10]);
      assert.equal(png.bytes.readUInt32BE(16),1920);assert.equal(png.bytes.readUInt32BE(20),1080);
      const text=await page.evaluate(()=>window.figureText);
      assert.ok(text.includes(rms.toFixed(6)));assert.ok(text.includes(drop.toFixed(6)+' m'));
      assert.ok(text.some(t=>t.includes('Sample 61 / 120')&&t.includes('2.033333 s')&&t.includes('Blender frame 62')));
      assert.ok(text.some(t=>t.includes(fingerprint)));
      // The record's portable fragment restores the exported view, across a fresh page load.
      await page.goto(url+record.replay_fragment);await page.reload();
      assert.deepEqual((await download('#figure')).bytes,png.bytes);
      await page.locator('#separate').click();
      const separate=JSON.parse((await download('#sample-json')).bytes);
      assert.deepEqual(separate.presentation.display_offsets_x_m,[-1.35,0,1.35]);
      assert.deepEqual(separate.metrics,record.metrics);
      assert.notDeepEqual((await download('#figure')).bytes,png.bytes);
      const chooser=page.waitForEvent('filechooser');
      await page.locator('#open-sample').click();
      await (await chooser).setFiles({name:recordFile.name,mimeType:'application/json',buffer:recordFile.bytes});
      await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Verified sample 61'));
      assert.equal(await page.locator('#overlay').getAttribute('aria-pressed'),'true');
      assert.equal(createHash('sha256').update((await download('#figure')).bytes).digest('hex'),createHash('sha256').update(png.bytes).digest('hex'));
      const temporary=await mkdtemp(join(tmpdir(),'cloth-sample-'));
      try{
        const file=join(temporary,'sample.json');await writeFile(file,recordFile.bytes);
        const checked=spawnSync('python3',['-S','-m','robot_reel.cli','cloth','--output','docs/cloth','--verify-sample',file],{encoding:'utf8',timeout:30000});
        assert.equal(checked.status,0,checked.stderr);
        const proof=JSON.parse(checked.stdout);assert.equal(proof.sample,61);assert.equal(proof.case_index,1);assert.equal(proof.recorded_facts_match,true);assert.equal(proof.positions_sha256,fingerprint);
      }finally{await rm(temporary,{recursive:true,force:true});}
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
    }finally{await page.close();}
  }
});
test('Cloth sample import rejects changed facts and ambiguous files without changing the current view',async()=>{
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[],network=[];
  page.on('pageerror',e=>errors.push(e.message));await page.route(/^https?:/,route=>{network.push(route.request().url());return route.abort();});
  try{
    await page.goto(pathToFileURL(resolve('docs/cloth/index.html')).href+'#frame=61&case=1&view=overlay&yaw=-0.9');
    const state=async()=>({frame:await page.locator('#timeline').inputValue(),image:createHash('sha256').update(await page.locator('#scene').evaluate(c=>c.toDataURL())).digest('hex'),url:page.url()});
    const before=await state(),fixture=JSON.parse(await readFile('tests/fixtures/cloth-sample.json','utf8'));
    const invalid=[];
    for(const mutate of [
      r=>{r.metrics.rms_separation_m=.909;},r=>{r.metrics.max_pin_displacement_m=true;},
      r=>{r.source.positions_sha256='0'.repeat(64);},r=>{r.source.independent_cases=1;},
      r=>{r.source.device='cpu';},r=>{r.source.frame_count=120;},r=>{r.sample=121;},
      r=>{r.sample=true;},r=>{r.case.index=3;},r=>{r.case.edge_ke=1;},
      r=>{r.presentation.yaw_rad=4;},r=>{r.presentation.pitch_rad=1;},
      r=>{r.presentation.display_offsets_x_m=[0,0,0];},r=>{r.time_s=0;},
      r=>{r.blender_frame=29;},r=>{r.limits=[];},r=>{r.verified=true;},
      r=>{r.replay_fragment+='\u0026yaw=0';},r=>{r.replay_fragment='https://example.com/';},
    ]){const record=structuredClone(fixture);mutate(record);invalid.push(Buffer.from(JSON.stringify(record)));}
    invalid.push(
      Buffer.from('{"sample":0,"\\u0073ample":29,'+JSON.stringify(fixture).slice(1)),
      Buffer.from('{"x":1e999}'),Buffer.alloc(65537,32),Buffer.from([255]),
      Buffer.from('['.repeat(2000)+']'.repeat(2000)),Buffer.from('null'),Buffer.from('{'),
    );
    for(const [index,buffer] of invalid.entries()){
      await page.locator('#sample-file').setInputFiles({name:`invalid-${index}.json`,mimeType:'application/json',buffer});
      await page.waitForFunction(()=>!document.querySelector('#sample-file').value&&document.querySelector('#status').textContent.startsWith('Could not open sample:'));
      assert.deepEqual(await state(),before,`invalid sample ${index} must not change the view`);
    }
    const valid=Buffer.concat([Buffer.from([239,187,191]),Buffer.from(JSON.stringify(fixture))]);
    await page.locator('#sample-file').setInputFiles({name:'valid.json',mimeType:'application/json',buffer:valid});
    await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Verified sample 29'));
    assert.equal(await page.locator('#timeline').inputValue(),'29');
    assert.equal(await page.locator('#separate').getAttribute('aria-pressed'),'true');
    assert.equal(await page.locator('#cases button[aria-pressed="true"]').textContent(),'k = 100CASE 3');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    assert.deepEqual(errors,[]);assert.deepEqual(network,[]);
  }finally{await page.close();}
});
test('Cloth sample imports ignore an older file that finishes reading after the latest choice',async()=>{
  const page=await browser.newPage();
  try{
    await page.goto(base+'/cloth/#frame=61&case=1&view=overlay&yaw=-0.9');
    const download=page.waitForEvent('download');await page.locator('#sample-json').click();
    const latest=await readFile(await (await download).path()),old=await readFile('tests/fixtures/cloth-sample.json');
    await page.evaluate(()=>{
      const original=File.prototype.arrayBuffer;
      File.prototype.arrayBuffer=function(){
        if(this.name!=='slow.json')return original.call(this);
        return new Promise(resolve=>{window.finishSampleRead=()=>original.call(this).then(resolve);});
      };
    });
    await page.locator('#sample-file').setInputFiles({name:'slow.json',mimeType:'application/json',buffer:old});
    await page.waitForFunction(()=>typeof window.finishSampleRead==='function');
    await page.locator('#sample-file').setInputFiles({name:'latest.json',mimeType:'application/json',buffer:latest});
    await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Verified sample 61'));
    const image=await page.locator('#scene').evaluate(c=>c.toDataURL());
    await page.evaluate(()=>window.finishSampleRead());
    assert.equal(await page.locator('#timeline').inputValue(),'61');
    assert.equal(await page.locator('#scene').evaluate(c=>c.toDataURL()),image);
    assert.match(await page.locator('#status').textContent(),/^Verified sample 61/);
  }finally{await page.close();}
});
test('Cloth PNG export freezes its sample during encoding and recovers from an encoder failure',async()=>{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  try{
    await page.goto(base+'/cloth/#frame=61&case=1&view=separate');
    await page.evaluate(()=>{
      window.originalToBlob=HTMLCanvasElement.prototype.toBlob;
      HTMLCanvasElement.prototype.toBlob=function(cb,type){window.originalToBlob.call(this,blob=>{window.finishFigure=()=>cb(blob);},type);};
    });
    const pending=page.waitForEvent('download');await page.locator('#figure').click();
    await page.waitForFunction(()=>typeof window.finishFigure==='function');
    await page.locator('#next').click();
    assert.equal(await page.locator('#timeline').inputValue(),'62');
    assert.equal(await page.locator('#figure').isDisabled(),true);
    await page.evaluate(()=>window.finishFigure());
    const frozen=await pending;
    assert.equal(frozen.suggestedFilename(),'robot-reel-cloth-bend_1-sample-061.png');
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('sample 61 saved'));
    assert.equal(await page.locator('#timeline').inputValue(),'62');
    await page.evaluate(()=>{HTMLCanvasElement.prototype.toBlob=function(cb){cb(null);};});
    await page.locator('#figure').click();
    assert.match(await page.locator('#status').textContent(),/Could not save the figure/);
    assert.equal(await page.locator('#figure').isDisabled(),false);
    await page.evaluate(()=>{HTMLCanvasElement.prototype.toBlob=window.originalToBlob;});
    const retry=page.waitForEvent('download');await page.locator('#figure').click();
    assert.equal((await retry).suggestedFilename(),'robot-reel-cloth-bend_1-sample-062.png');
    await page.goto(base+'/cloth/#frame=61&case=1&view=separate');
    await page.reload();
    const fresh=page.waitForEvent('download');await page.locator('#figure').click();
    const checksum=bytes=>createHash('sha256').update(bytes).digest('hex');
    assert.equal(checksum(await readFile(await (await fresh).path())),checksum(await readFile(await frozen.path())));
    for(const angle of ['NaN','Infinity','1e99','', '-4']){
      await page.goto(base+'/cloth/#frame=61&case=1&view=separate&yaw='+angle);
      const record=page.waitForEvent('download');await page.locator('#sample-json').click();
      assert.equal(JSON.parse(await readFile(await (await record).path())).presentation.yaw_rad,-.48);
    }
    assert.deepEqual(errors,[]);
  }finally{await page.close();}
});
test('Cloth Lab works offline on mobile with explicit playback and bounded shared selections',async()=>{
  const page=await browser.newPage({viewport:{width:390,height:844},reducedMotion:'reduce'});
  const errors=[],requests=[];page.on('pageerror',error=>errors.push(error.message));
  try{
    await page.route(/^https?:/,route=>{requests.push(route.request().url());return route.abort();});
    const url=pathToFileURL(resolve('docs/cloth/index.html')).href;
    await page.goto(url+'#case=999&frame=999&view=overlay');
    assert.equal(await page.locator('#counter').textContent(),'Sample 120 / 120');
    assert.equal(await page.locator('#next').isDisabled(),true);
    assert.equal(await page.locator('#cases button[aria-pressed="true"]').textContent(),'k = 100CASE 3');
    assert.equal(await page.locator('#download-archive').isVisible(),false);
    assert.equal(await page.locator('#play').textContent(),'Play ▶');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.locator('#start').click();
    assert.equal(await page.locator('#prev').isDisabled(),true);
    assert.equal(await page.locator('#distance').textContent(),'0.000');
    assert.equal(await page.locator('#drop').textContent(),'0.000 m');
    await page.locator('#play').click();
    await page.waitForFunction(()=>Number(document.querySelector('#timeline').value)>=3);
    await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});
    assert.equal(await page.locator('#play').textContent(),'Play ▶');
    const frame=await page.locator('#timeline').inputValue();
    await page.locator('#share').click();
    assert.match(await page.locator('#status').textContent(),/Share the experiment folder/);
    await page.reload();
    assert.equal(await page.locator('#timeline').inputValue(),frame);
    await page.goto(url+'#frame=-2&case=NaN&view=invalid');
    await page.reload();
    assert.equal(await page.locator('#counter').textContent(),'Sample 29 / 120');
    assert.equal(await page.locator('#separate').getAttribute('aria-pressed'),'true');
    assert.deepEqual(requests,[]);
    assert.deepEqual(errors,[]);
  }finally{await page.close();}
});
test('Cloth Lab keeps original scene downloads available without JavaScript',async()=>{
  const page=await browser.newPage({javaScriptEnabled:false,viewport:{width:390,height:844}});
  try{
    await page.goto(base+'/cloth/');
    const pending=page.waitForEvent('download');
    await page.getByRole('link',{name:'OpenUSD scene ↓',exact:true}).click();
    assert.deepEqual(await readFile(await (await pending).path()),await readFile('docs/cloth/scene.usdc'));
    assert.match(await page.locator('noscript').textContent(),/original data or USD/);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  }finally{await page.close();}
});
test('Stress Lab pairs real traces and inspects shared samples and terminal controls',async()=>{
  const page=await browser.newPage();
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  try{
    const {data,seed,condition,reference,other,max,shorter}=await stressExample();
    await page.goto(base+`/stress/#seed=${seed}&condition=${condition}&frame=0`);
    await page.waitForFunction(()=>[...document.querySelectorAll('video')].every(v=>v.readyState>=2&&!v.seeking));
    assert.deepEqual(await page.locator('#stress-data').textContent().then(JSON.parse),data);
    assert.equal(await page.locator('#matrix button').count(),30);
    assert.equal(await page.locator('#runs tr').count(),30);
    assert.equal(await page.locator('#attempts tr').count(),data.summary.attempts);
    assert.equal(await page.locator('#left-inference').textContent(),`Chunk from sample 0 · policy ${reference.inference_calls[0].policy_seconds.toFixed(2)} s · this simulation step ${(reference.frames[0].env_step_seconds*1000).toFixed(0)} ms`);
    await page.locator('#next-call').click();
    assert.match(await page.locator('#counter').textContent(),/^Sample 10 /);
    await page.waitForFunction(()=>[...document.querySelectorAll('video')].every(v=>!v.seeking));
    await page.locator('#play').click();
    await page.waitForFunction(()=>Number(document.querySelector('#timeline').value)>=20);
    assert.ok(await page.evaluate(()=>Math.abs(document.querySelector('#left-video').currentTime-document.querySelector('#right-video').currentTime)<.06));
    await page.locator('#play').click();
    await page.waitForFunction(()=>[...document.querySelectorAll('video')].every(v=>!v.seeking));
    assert.ok(await page.evaluate(()=>Math.abs(document.querySelector('#left-video').currentTime-document.querySelector('#right-video').currentTime)<.005));
    await page.locator('#peak').click();
    const peak=data.summary.pairs.find(p=>p.seed===seed&&p.condition===condition);
    assert.match(await page.locator('#counter').textContent(),new RegExp(`^Sample ${peak.max_eef_frame} /`));
    assert.equal(await page.locator('#distance').textContent(),`${(peak.max_eef_distance_m*100).toFixed(1)} cm EEF separation`);
    await page.locator('#terminal').click();
    assert.match(await page.locator('#counter').textContent(),new RegExp(`^Sample ${other.result.actions} /`));
    assert.equal(await page.locator('#right-inference').textContent(),'Terminal observation · no action');
    assert.deepEqual(await page.locator('#right-controls .value').allTextContents(),Array(7).fill('—'));
    await page.locator('#timeline').evaluate(el=>{el.value=el.max;el.dispatchEvent(new Event('input',{bubbles:true}));});
    await page.waitForFunction(()=>[...document.querySelectorAll('video')].every(v=>!v.seeking));
    const shortTrace=shorter==='left'?reference:other,unequal=reference.result.actions!==other.result.actions;
    assert.match(await page.locator(`#${shorter}-clock`).textContent(),unequal?/HELD FINAL/:/FINAL OBSERVATION/);
    assert.equal(await page.locator(`#${shorter}-video`).getAttribute('data-frame'),String(shortTrace.result.actions));
    if(unequal)assert.equal(await page.locator('#distance').textContent(),'Outside the shared recording');
    assert.ok(Math.abs(await page.locator(`#${shorter}-video`).evaluate(v=>v.currentTime)-shortTrace.result.simulation_seconds)<.01);
    await page.locator('#wrist').click();
    await page.waitForFunction(()=>[...document.querySelectorAll('video')].every(v=>v.readyState>=2&&!v.seeking));
    assert.match(await page.locator('#right-video').getAttribute('src'),/wrist.mp4$/);
    assert.match(await page.locator('#counter').textContent(),new RegExp(`^Sample ${max} /`));
    await page.locator('#share').click();await page.reload();
    assert.equal(await page.locator('#wrist').getAttribute('aria-pressed'),'true');
    assert.match(await page.locator(`#${shorter}-clock`).textContent(),unequal?/HELD FINAL/:/FINAL OBSERVATION/);
    const pending=page.waitForEvent('download');
    await page.getByRole('link',{name:'MCAP telemetry ↓',exact:true}).click();
    assert.deepEqual(await readFile(await (await pending).path()),await readFile('docs/stress/telemetry.mcap'));
    assert.deepEqual(errors,[]);
  }finally{await page.close();}
});
test('Paired outcome groups retain gains and losses and export the complete source-checked report',async()=>{
  const directory=await mkdtemp(join(tmpdir(),'robot-reel-pairs-'));
  try{
    for(const width of [1280,390]){
      const page=await browser.newPage({viewport:{width,height:900},reducedMotion:'reduce'});
      const errors=[],requests=[];page.on('pageerror',e=>errors.push(e.message));
      try{
        await page.route(/^https?:/,route=>{requests.push(route.request().url());route.abort();});
        await page.goto(pathToFileURL(resolve('docs/stress/index.html')).href+'#seed=9&condition=dim&frame=0');
        assert.deepEqual(await page.locator('#outcome-cells strong').allTextContents(),['4','1','0','5']);
        await page.locator('#outcome-condition').selectOption('camera');
        assert.deepEqual(await page.locator('#outcome-cells strong').allTextContents(),['4','1','3','2']);
        await page.locator('[data-outcome="lost_success"]').click();
        assert.deepEqual(await page.locator('#outcome-seeds button').allTextContents(),['Seed 09']);
        await page.locator('#outcome-seeds button').click();
        assert.equal(await page.locator('#seed').inputValue(),'9');
        assert.equal(await page.locator('#condition').inputValue(),'camera');
        assert.match(await page.locator('#left-outcome').textContent(),/Success/);
        assert.match(await page.locator('#right-outcome').textContent(),/Step limit/);
        const pending=page.waitForEvent('download');await page.locator('#outcome-download').click();
        const raw=await readFile(await (await pending).path(),'utf8');
        const report=JSON.parse(raw);
        assert.equal(report.comparisons.length,2);
        assert.equal(report.scope.planned_trials,30);
        assert.equal(report.comparisons[1].net_success_difference,2);
        const output=join(directory,`paired-${width}.json`);await writeFile(output,raw);
        const checked=spawnSync('python3',['-S','-m','robot_reel.cli','stress','docs/stress','--paired-report',output],{encoding:'utf8'});
        assert.equal(checked.status,0,checked.stderr);
        assert.equal(JSON.parse(checked.stdout).paired_report_verified,true);
        const exported=spawnSync('python3',['-S','-m','robot_reel.cli','stress','docs/stress','--paired'],{encoding:'utf8'});
        assert.equal(exported.status,0,exported.stderr);
        assert.deepEqual(JSON.parse(exported.stdout),report);
        await page.locator('#outcome-condition').selectOption('dim');
        await page.locator('[data-outcome="gained_success"]').click();
        assert.equal(await page.locator('#outcome-seeds button').count(),0);
        assert.match(await page.locator('#outcome-selection').textContent(),/No recorded pair/);
        await page.locator('#outcome-all').click();
        assert.equal(await page.locator('#outcome-seeds button').count(),10);
        assert.equal(await page.locator('#matrix button').count(),30);
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
        assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
      }finally{await page.close();}
    }
  }finally{await rm(directory,{recursive:true,force:true});}
});
test('Stress Lab is offline, accessible on mobile and keeps all seed choices',async()=>{
  const page=await browser.newPage({viewport:{width:390,height:844},reducedMotion:'reduce'});
  const errors=[],requests=[];page.on('pageerror',error=>errors.push(error.message));
  try{
    await page.route(/^https?:/,route=>{requests.push(route.request().url());route.abort();});
    await page.goto(pathToFileURL(resolve('docs/stress/index.html')).href+'#seed=0&condition=dim&frame=0');
    await page.waitForFunction(()=>[...document.querySelectorAll('video')].every(v=>v.readyState>=2&&!v.seeking));
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    assert.equal(await page.locator('#play').textContent(),'Play ▶');
    assert.equal(await page.locator('#zip').isVisible(),false);
    await page.locator('#seed').selectOption('9');
    await page.locator('#condition').selectOption('camera');
    assert.equal(await page.locator('#matrix button[aria-pressed=true]').getAttribute('data-seed'),'9');
    assert.equal(await page.locator('#matrix button[aria-pressed=true]').getAttribute('data-condition'),'camera');
    await page.locator('#timeline').focus();await page.keyboard.press('ArrowRight');
    assert.match(await page.locator('#counter').textContent(),/^Sample 1 /);
    await page.locator('#share').click();
    assert.match(await page.locator('#status').textContent(),/^Share this complete folder/);
    assert.match(page.url(),/#seed=9&condition=camera&frame=1&camera=main$/);
    await page.locator('#matrix button[data-seed="3"][data-condition="reference"]').click();
    assert.equal(await page.locator('#condition').inputValue(),'reference');
    assert.equal(await page.locator('#distance').textContent(),'0.0 cm EEF separation');
    assert.deepEqual(requests,[]);assert.deepEqual(errors,[]);
  }finally{await page.close();}
});
test('Failure review keeps denominators and opens the measured tail window',async()=>{
  const taxonomy=JSON.parse(await readFile('docs/stress/reliability.json','utf8'));
  for(const width of [1440,390,320]){
    const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'}),errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    try{
      const url=width===320?pathToFileURL(resolve('docs/stress/index.html')).href:base+'/stress/';
      await page.goto(url);
      assert.equal(await page.locator('#failure-trials button').count(),14);
      for(const id of taxonomy.kinds.step_limit_in_motion)
        assert.equal(await page.locator(`#failure-trials [data-trial="${id}"]`).count(),1);
      await page.locator('#failure-trials [data-trial="seed-02-camera"]').click();
      assert.equal(await page.locator('#seed').inputValue(),'2');
      assert.equal(await page.locator('#condition').inputValue(),'camera');
      assert.match(await page.locator('#failure-detail').textContent(),/44\.8 mm.*145–160/);
      assert.match(await page.locator('#counter').textContent(),/^Sample 145 /);
      assert.equal(await page.evaluate(()=>document.activeElement.id),'play');
      await page.locator('#failure-kind').selectOption('step_limit_stalled');
      assert.match(await page.locator('#failure-count').textContent(),/No recorded trial matches/);
      assert.equal(await page.locator('#matrix button').count(),30);
      await page.locator('#failure-kind').selectOption('success');
      assert.equal(await page.locator('#failure-trials button').count(),16);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      assert.deepEqual(errors,[]);
    }finally{await page.close();}
  }
});
test('Stress Lab bounds shared inputs and finishes on real final observations',async()=>{
  const page=await browser.newPage();
  try{
    const {seed,condition,reference,other,max,shorter}=await stressExample(true);
    await page.goto(base+'/stress/#seed=9999&condition=unknown&frame=99999&camera=bad');
    assert.equal(await page.locator('#seed').inputValue(),'9');
    assert.equal(await page.locator('#main').getAttribute('aria-pressed'),'true');
    assert.equal(await page.locator('#next').isDisabled(),true);
    await page.evaluate(hash=>{location.hash=hash;},`seed=${seed}&condition=${condition}&frame=${max-1}&camera=main`);
    await page.waitForFunction(n=>Number(document.querySelector('#timeline').value)===n&&[...document.querySelectorAll('video')].every(v=>v.readyState>=2&&!v.seeking),max-1);
    await page.locator('#play').click();
    await page.waitForFunction(()=>document.querySelector('#status').textContent==='End of the recorded pair. Final observations have no action.');
    assert.equal(await page.locator('#timeline').inputValue(),String(max));
    assert.equal(await page.locator('#left-inference').textContent(),'Terminal observation · no action');
    assert.equal(await page.locator('#right-inference').textContent(),'Terminal observation · no action');
    assert.match(await page.locator(`#${shorter}-clock`).textContent(),reference.result.actions!==other.result.actions?/HELD FINAL/:/FINAL OBSERVATION/);
  }finally{await page.close();}
});
test('Stress review downloads survive CLI verification and offline import without changing source facts',async()=>{
  const page=await browser.newPage({viewport:{width:390,height:844}});
  const folder=await mkdtemp(join(tmpdir(),'robot-reel-review-'));
  const errors=[],requests=[];
  const note='检查接触点 🔎\n````\n<img src=x onerror="window.injected=true">\n[link](javascript:alert(1))\n````';
  page.on('pageerror',e=>errors.push(e.message));
  await page.route(/^https?:/,route=>{requests.push(route.request().url());route.abort();});
  try{
    await page.goto(pathToFileURL(resolve('docs/stress/index.html')).href+'#seed=9&condition=dim&frame=61&camera=wrist');
    await page.locator('#review-note').fill(note);
    let saved;
    for(const frame of [61,82,100,160]){
      await page.locator('#timeline').evaluate((el,n)=>{el.value=n;el.dispatchEvent(new Event('input'));},frame);
      const pending=page.waitForEvent('download');await page.locator('#review-json').click();
      const download=await pending,review=JSON.parse(await readFile(await download.path(),'utf8'));
      assert.equal(download.suggestedFilename(),`robot-reel-seed-09-dim-sample-${frame}-wrist.json`);
      assert.equal(review.scope.planned_trials,30);assert.equal(review.user_note,note);
      assert.equal(review.recorded[0].source_frame,Math.min(82,frame));
      assert.equal(review.recorded[0].held_final,frame>82);
      if(frame>=82){assert.equal(review.recorded[0].observation.action,null);assert.equal(review.recorded[0].active_inference,null);}
      const output=join(folder,download.suggestedFilename());await download.saveAs(output);
      const check=spawnSync('python3',['-S','-m','robot_reel.cli','stress','docs/stress','--review',output],{encoding:'utf8'});
      assert.equal(check.status,0,check.stderr);
      assert.equal(JSON.parse(check.stdout).review.recorded_facts_match,true);
      if(frame===100)saved={output,review};
    }
    await page.locator('#seed').selectOption('0');
    await page.locator('#review-note').fill('Local draft');
    await page.locator('#review-file').setInputFiles(saved.output);
    await page.waitForFunction(()=>document.querySelector('#review-status').textContent.startsWith('Recorded facts match'));
    assert.equal(await page.locator('#seed').inputValue(),'9');
    assert.equal(await page.locator('#condition').inputValue(),'dim');
    assert.equal(await page.locator('#timeline').inputValue(),'100');
    assert.equal(await page.locator('#wrist').getAttribute('aria-pressed'),'true');
    assert.match(page.url(),/#seed=9&condition=dim&frame=100&camera=wrist$/);
    assert.match(await page.locator('#left-clock').textContent(),/SOURCE 082.*HELD FINAL/);
    assert.equal(await page.locator('#review-note').inputValue(),note);
    assert.equal(await page.evaluate(()=>window.injected),undefined);
    const pending=page.waitForEvent('download');await page.locator('#review-md').click();
    const markdown=await readFile(await (await pending).path(),'utf8');
    assert.ok(markdown.includes('`````text\n'+note+'\n`````'));
    assert.match(markdown,/30\/30 trials completed/);
    assert.match(markdown,/\| seed-09-reference \| success \| 82 \| 4.10 s \| HELD FINAL \|/);
    assert.match(markdown,/index.html#seed=9&condition=dim&frame=100&camera=wrist/);
    assert.ok(!markdown.includes('file:///')&&!markdown.includes('127.0.0.1'));
    const corrupted=structuredClone(saved.review);corrupted.scope.planned_trials=2;
    await page.locator('#review-file').setInputFiles({name:'changed.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(corrupted))});
    await page.waitForFunction(()=>document.querySelector('#review-status').textContent.startsWith('Could not open review:'));
    assert.match(await page.locator('#review-status').textContent(),/facts differ/);
    assert.equal(await page.locator('#timeline').inputValue(),'100');
    assert.equal(await page.locator('#review-note').inputValue(),note);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.locator('#review-clear').click();assert.equal(await page.locator('#review-note').inputValue(),'');
    assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
  }finally{await page.close();await rm(folder,{recursive:true,force:true});}
});
test('Stress review rejects malformed and oversized imports and does not store notes between visits',async()=>{
  const page=await browser.newPage();
  try{
    await page.goto(base+'/stress/#seed=9&condition=reference&frame=61&camera=main');
    await page.locator('#review-note').fill('Draft');
    for(const buffer of [Buffer.from('null'),Buffer.from('{'),Buffer.alloc(131073,32)]){
      await page.locator('#review-file').setInputFiles({name:'invalid.json',mimeType:'application/json',buffer});
      await page.waitForFunction(()=>document.querySelector('#review-file').value==='');
      assert.match(await page.locator('#review-status').textContent(),/^Could not open review:/);
      assert.equal(await page.locator('#review-note').inputValue(),'Draft');
      assert.equal(await page.locator('#timeline').inputValue(),'61');
    }
    const pending=page.waitForEvent('download');await page.locator('#review-json').click();
    const review=JSON.parse(await readFile(await (await pending).path(),'utf8'));
    assert.deepEqual(review.recorded[0],review.recorded[1]);
    await page.reload();assert.equal(await page.locator('#review-note').inputValue(),'');
    assert.equal(await page.locator('#matrix button').count(),30);
  }finally{await page.close();}
});
test('Butterfly Lab preserves source metrics across views, playback, sharing and USD download',async()=>{
  const page=await browser.newPage();
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  try{
    await page.goto(base+'/chaos/#frame=0&world=11&view=overlay');
    assert.equal(await page.locator('#counter').textContent(),'Sample 0 / 600');
    assert.equal(await page.locator('#pair').textContent(),'World 12');
    assert.equal(await page.locator('#angle').textContent(),'+0.55°');
    assert.equal(await page.locator('#distance').textContent(),'0.031');
    assert.equal(await page.locator('#overlay').getAttribute('aria-pressed'),'true');
    await page.locator('#peak').click();
    assert.equal(await page.locator('#counter').textContent(),'Sample 375 / 600');
    assert.equal(await page.locator('#time').textContent(),'12.500');
    assert.equal(await page.locator('#distance').textContent(),'6.260');
    assert.equal(await page.locator('#pair').textContent(),'World 04');
    assert.equal(await page.locator('#angle').textContent(),'+0.15°');
    assert.equal(await page.locator('#initial-distance').textContent(),'0.0084 m');
    const before=await page.locator('#scene').evaluate(canvas=>canvas.toDataURL());
    await page.locator('#sculpture').click();
    assert.equal(await page.locator('#scene').evaluate(canvas=>canvas.toDataURL())===before,false);
    assert.equal(await page.locator('#distance').textContent(),'6.260');
    assert.equal(await page.locator('#counter').textContent(),'Sample 375 / 600');
    await page.locator('#share').click();
    assert.match(page.url(),/#frame=375&world=3&view=sculpture$/);
    await page.reload();
    assert.equal(await page.locator('#counter').textContent(),'Sample 375 / 600');
    assert.equal(await page.locator('#pair').textContent(),'World 04');
    await page.locator('#next').click();
    assert.equal(await page.locator('#dcc-frame').textContent(),'Blender frame 377');
    await page.locator('#play').click();
    await page.waitForFunction(()=>Number(document.querySelector('#timeline').value)>380);
    await page.locator('#play').click();
    assert.match(await page.locator('#status').textContent(),/^Paused/);
    const pending=page.waitForEvent('download');
    await page.getByRole('link',{name:'Open in Blender ↓'}).click();
    const download=await pending;
    assert.equal(download.suggestedFilename(),'scene.usdc');
    assert.deepEqual(await readFile(await download.path()),await readFile('docs/chaos/scene.usdc'));
    assert.deepEqual(errors,[]);
  }finally{await page.close();}
});
test('Butterfly Lab stays offline and paused on mobile, supports camera and keyboard controls',async()=>{
  const page=await browser.newPage({viewport:{width:390,height:844},reducedMotion:'reduce'});
  const errors=[],requests=[];page.on('pageerror',error=>errors.push(error.message));
  try{
    await page.route(/^https?:/,route=>{requests.push(route.request().url());route.abort();});
    await page.goto(pathToFileURL(resolve('docs/chaos/index.html')).href);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    assert.equal(await page.locator('#counter').textContent(),'Sample 375 / 600');
    const before=await page.locator('#scene').evaluate(canvas=>canvas.toDataURL());
    await page.locator('#rotate-right').click();
    assert.equal(await page.locator('#scene').evaluate(canvas=>canvas.toDataURL())===before,false);
    assert.equal(await page.locator('#counter').textContent(),'Sample 375 / 600');
    await page.locator('#reset-view').click();
    // Read the canvas pixels: scrolled element screenshots can differ in
    // compositor antialiasing even after the camera returns to the same pose.
    assert.equal(await page.locator('#scene').evaluate(canvas=>canvas.toDataURL())===before,true);
    await page.locator('#scene').scrollIntoViewIfNeeded();
    const box=await page.locator('#scene').boundingBox();
    await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();
    await page.mouse.move(box.x+box.width/2+40,box.y+box.height/2);await page.mouse.up();
    assert.equal(await page.locator('#scene').evaluate(canvas=>canvas.toDataURL())===before,false);
    await page.locator('#scene').focus();await page.keyboard.press('ArrowRight');
    assert.equal(await page.locator('#counter').textContent(),'Sample 376 / 600');
    await page.getByRole('button',{name:'World 1, +0.00 degrees',exact:true}).click();
    assert.equal(await page.locator('#distance').textContent(),'0.000');
    await page.locator('#start').click();
    assert.equal(await page.locator('#counter').textContent(),'Sample 0 / 600');
    assert.equal(await page.locator('#prev').isDisabled(),true);
    await page.locator('#timeline').evaluate(el=>{el.value=el.max;el.dispatchEvent(new Event('input',{bubbles:true}));});
    assert.equal(await page.locator('#counter').textContent(),'Sample 600 / 600');
    assert.equal(await page.locator('#time').textContent(),'20.000');
    assert.equal(await page.locator('#next').isDisabled(),true);
    await page.locator('#share').click();
    assert.match(await page.locator('#status').textContent(),/^Share this folder/);
    assert.deepEqual(requests,[]);assert.deepEqual(errors,[]);
  }finally{await page.close();}
});
test('Butterfly Lab bounds shared indices and finishes playback on the last real sample',async()=>{
  const page=await browser.newPage();
  try{
    await page.goto(base+'/chaos/#frame=999999&world=9999&view=unknown');
    assert.equal(await page.locator('#counter').textContent(),'Sample 600 / 600');
    assert.equal(await page.locator('#pair').textContent(),'World 12');
    assert.equal(await page.locator('#sculpture').getAttribute('aria-pressed'),'true');
    await page.evaluate(()=>{location.hash='frame=599&world=3&view=overlay';});
    await page.waitForFunction(()=>document.querySelector('#timeline').value==='599');
    await page.locator('#play').click();
    await page.waitForFunction(()=>document.querySelector('#play').textContent==='Play ▶');
    assert.equal(await page.locator('#counter').textContent(),'Sample 600 / 600');
    assert.equal(await page.locator('#time').textContent(),'20.000');
    assert.equal(await page.locator('#status').textContent(),'End of the recorded experiment.');
  }finally{await page.close();}
});
test('physics-to-cinema divider preserves source clocks, contact and scene download',async()=>{
  const page=await browser.newPage();
  try{
    await page.goto(base+'/remix/#frame=119');
    await page.waitForFunction(()=>[...document.querySelectorAll('video')].every(v=>v.readyState>=2&&!v.seeking));
    assert.equal(await page.locator('#counter').textContent(),'Sample 119 / 179');
    await page.locator('#show-raw').click();
    assert.equal(await page.locator('#reveal').inputValue(),'100');
    await page.locator('#show-rendered').click();
    assert.equal(await page.locator('#reveal').inputValue(),'0');
    assert.equal(await page.locator('#counter').textContent(),'Sample 119 / 179');
    await page.locator('#show-split').click();
    assert.equal(await page.locator('#reveal').inputValue(),'50');
    await page.locator('#contact').click();
    await page.waitForFunction(()=>[...document.querySelectorAll('video')].every(v=>!v.seeking));
    assert.equal(await page.locator('#sample').textContent(),'107');
    assert.match(await page.locator('#left-state').textContent(),/NO CONTACT YET/);
    assert.match(await page.locator('#right-state').textContent(),/CONTACT RECORDED/);
    assert.equal(await page.locator('#dcc-frame').textContent(),'108');
    await page.locator('#play').click();
    await page.waitForFunction(()=>Number(document.querySelector('#sample').textContent)>115);
    await page.locator('#play').click();
    assert.ok(await page.evaluate(()=>Math.abs(document.querySelector('#raw').currentTime-document.querySelector('#rendered').currentTime)<.07));
    await page.locator('#share').click();
    assert.ok(page.url().endsWith('#frame='+await page.locator('#sample').textContent()));
    const pending=page.waitForEvent('download');
    await page.getByRole('link',{name:'Take the Blender scene ↓'}).click();
    assert.deepEqual(await readFile(await (await pending).path()),await readFile('docs/blender/replay.blend'));
  }finally{await page.close();}
});
test('physics-to-cinema works offline on mobile with keyboard and pointer controls',async()=>{
  const page=await browser.newPage({viewport:{width:390,height:844}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  try{
    await page.route(/^https?:/,route=>route.abort());
    await page.goto(pathToFileURL(resolve('docs/remix/index.html')).href);
    await page.waitForFunction(()=>[...document.querySelectorAll('video')].every(v=>v.readyState>=2&&!v.seeking));
    const initial=await page.locator('#stage').screenshot();
    await page.evaluate(()=>{location.hash='frame=0';});
    await page.waitForFunction(()=>[...document.querySelectorAll('video')].every(v=>!v.seeking));
    assert.deepEqual(await page.locator('#stage').screenshot(),initial,'Initial view must show frame 0, not an unrelated poster');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.locator('#reveal').focus();await page.keyboard.press('ArrowRight');
    assert.equal(await page.locator('#reveal').inputValue(),'51');
    await page.locator('#next').focus();await page.keyboard.press('Enter');
    await page.waitForFunction(()=>document.querySelector('#sample').textContent==='1');
    await page.locator('#handle').scrollIntoViewIfNeeded();
    const box=await page.locator('#handle').boundingBox();
    await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();
    await page.mouse.move(box.x+box.width/2+35,box.y+box.height/2);await page.mouse.up();
    assert.ok(Number(await page.locator('#reveal').inputValue())>55);
    assert.equal(await page.locator('#sample').textContent(),'1');
    await page.locator('#share').click();
    assert.match(await page.locator('#status').textContent(),/Share the demo folders/);
    assert.deepEqual(errors,[]);
  }finally{await page.close();}
});
test('director retains slow-motion sample mapping and exports edits separately',async()=>{
  const page=await browser.newPage();
  try{
    await page.goto(base+'/director/#frame=119');
    await page.waitForFunction(()=>document.querySelector('video').readyState>=2&&!document.querySelector('video').seeking);
    assert.equal(await page.locator('#counter').textContent(),'Frame 119 / 209');
    // Browser media clocks round fractional seconds; retain exact frame selection.
    for(const frame of [95, 97, 107, 125, 178, 209]){
      await page.locator('#timeline').evaluate((el,value)=>{el.value=String(value);el.dispatchEvent(new Event('input',{bubbles:true}));},frame);
      await page.waitForFunction(()=>!document.querySelector('video').seeking);
      assert.equal(await page.locator('#counter').textContent(),`Frame ${frame} / 209`);
    }
    await page.locator('.shot').nth(2).click();
    await page.waitForFunction(()=>document.querySelector('#source-frame').textContent==='96');
    assert.equal(await page.locator('#shot-label').textContent(),'SHOT 3 / 0.5×');
    await page.locator('#next').click();
    await page.waitForFunction(()=>document.querySelector('#counter').textContent==='Frame 97 / 209');
    assert.equal(await page.locator('#source-frame').textContent(),'96');
    await page.locator('#next').click();
    await page.waitForFunction(()=>document.querySelector('#source-frame').textContent==='97');
    await page.locator('.shot').last().click();
    await page.waitForFunction(()=>document.querySelector('#source-frame').textContent==='126');
    await page.locator('#share').click();
    assert.match(page.url(),/#frame=156$/);
    await page.locator('summary').click();
    await page.getByLabel('Shot 1 caption').fill('Show the measured decision.');
    await page.getByLabel('Shot 1 camera').selectOption('top');
    const pending=page.waitForEvent('download');
    await page.locator('#download-plan').click();
    const plan=JSON.parse(await readFile(await (await pending).path(),'utf8'));
    assert.equal(plan.shots[0].caption,'Show the measured decision.');
    assert.equal(plan.shots[0].camera,'top');
    assert.equal(await page.evaluate(()=>JSON.parse(document.querySelector('#director-data').textContent).plan.shots[0].camera),'overview');
    assert.equal(await page.locator('#source-frame').textContent(),'126');
    const project=page.waitForEvent('download');
    await page.getByRole('link',{name:'Blender project + sources ↓'}).click();
    assert.deepEqual(await readFile(await (await project).path()),await readFile('docs/director/project.zip'));
  }finally{await page.close();}
});
test('VLA synchronizes both camera views, applied controls and terminal observation',async()=>{
  const page=await browser.newPage();
  try{
    await page.goto(base+'/vla/#frame=35');
    await page.waitForFunction(()=>[...document.querySelectorAll('video')].every(v=>v.readyState>=1&&Math.abs(v.currentTime-1.75)<.01));
    assert.equal(await page.locator('#outcome').textContent(),'TASK SUCCESS');
    assert.match(await page.locator('#decision').textContent(),/observation 30$/);
    const expected=await page.evaluate(()=>JSON.parse(document.querySelector('#vla-data').textContent).frames[35].action.map(v=>v.toFixed(2)));
    assert.deepEqual(await page.locator('.number').allTextContents(),expected);
    await page.locator('#play').click();
    await page.waitForFunction(()=>document.querySelector('#main-video').currentTime>2);
    await page.locator('#play').click();
    assert.ok(await page.evaluate(()=>Math.abs(document.querySelector('#main-video').currentTime-document.querySelector('#wrist-video').currentTime)<.1));
    await page.locator('#timeline').evaluate(el=>{el.value=el.max;el.dispatchEvent(new Event('input',{bubbles:true}));});
    await page.waitForFunction(()=>document.querySelector('#counter').textContent==='Observation 76 / 76');
    assert.equal(await page.locator('#phase').textContent(),'TERMINAL OBSERVATION');
    assert.deepEqual(await page.locator('.number').allTextContents(),Array(7).fill('—'));
    assert.equal(await page.locator('#sim-time').textContent(),'4.300');
    await page.locator('#share').click();
    assert.match(page.url(),/#frame=76$/);
    const pending=page.waitForEvent('download');
    await page.getByRole('link',{name:'Download episode + evidence ↓'}).click();
    assert.deepEqual(await readFile(await (await pending).path()),await readFile('docs/vla/episode.zip'));
  }finally{await page.close();}
});
for(const pack of ['director','vla']){
  test(`${pack} works offline on mobile with keyboard stepping and no overflow`,async()=>{
    const page=await browser.newPage({viewport:{width:390,height:844}});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    try{
      await page.route(/^https?:/,route=>route.abort());
      await page.goto(pathToFileURL(resolve(`docs/${pack}/index.html`)).href);
      await page.waitForFunction(()=>[...document.querySelectorAll('video')].every(v=>v.readyState>=1));
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      if(pack==='vla')assert.equal(await page.getByRole('link',{name:'Download episode + evidence ↓'}).count(),0);
      await page.locator('#next').focus();await page.keyboard.press('Enter');
      await page.waitForFunction(()=>document.querySelector('#timeline').value==='1');
      await page.locator('#share').click();
      assert.match(await page.locator('#status').textContent(),/Share this folder/);
      assert.deepEqual(errors,[]);
    }finally{await page.close();}
  });
}
test('Newton replay steps real poses, shares a sample and downloads the exact USD',async()=>{
  const page=await browser.newPage();
  try{
    await page.goto(base+'/newton/#frame=30');
    assert.equal(await page.locator('#sample').textContent(),'30');
    assert.equal(await page.locator('#dcc-frame').textContent(),'31');
    assert.equal(await page.locator('#time').textContent(),'1.000');
    await page.locator('#body').selectOption('1');
    const expected=await page.evaluate(()=>JSON.parse(document.querySelector('#trace-data').textContent).frames[30].poses[1][0].toFixed(4)+' m');
    assert.equal(await page.locator('#x').textContent(),expected);
    const before=await page.locator('canvas').screenshot();
    await page.locator('#front').click();
    assert.notDeepEqual(await page.locator('canvas').screenshot(),before);
    assert.equal(await page.locator('#sample').textContent(),'30');
    await page.locator('#next').click();
    assert.equal(await page.locator('#sample').textContent(),'31');
    await page.locator('#share').click();
    assert.match(page.url(),/#frame=31$/);
    const pending=page.waitForEvent('download');
    await page.getByRole('link',{name:'Download USD scene ↓'}).click();
    const download=await pending;
    assert.equal(download.suggestedFilename(),'scene.usda');
    assert.deepEqual(await readFile(await download.path()),await readFile(resolve('docs/newton/scene.usda')));
    await page.locator('#play').click();
    await page.waitForFunction(()=>Number(document.querySelector('#sample').textContent)>31);
    await page.locator('#play').click();
  }finally{await page.close();}
});
test('Newton works offline on mobile and reaches the final source sample',async()=>{
  const page=await browser.newPage({viewport:{width:390,height:844}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  try{
    await page.route(/^https?:/,route=>route.abort());
    await page.goto(pathToFileURL(resolve('docs/newton/index.html')).href);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.locator('#next').focus();await page.keyboard.press('Enter');
    assert.equal(await page.locator('#sample').textContent(),'1');
    await page.locator('#timeline').evaluate(el=>{el.value=el.max;el.dispatchEvent(new Event('input',{bubbles:true}));});
    assert.equal(await page.locator('#frame-counter').textContent(),'Sample 180 of 180');
    assert.equal(await page.locator('#dcc-frame').textContent(),'181');
    assert.equal(await page.locator('#time').textContent(),'6.000');
    await page.locator('#next').click();
    assert.equal(await page.locator('#sample').textContent(),'180');
    await page.locator('#share').click();
    assert.match(await page.locator('#share').textContent(),/Share this folder/);
    assert.deepEqual(errors,[]);
  }finally{await page.close();}
});
test('Blender replay steps source samples and retains both contact outcomes',async()=>{
  const page=await browser.newPage();
  try{
    await page.goto(base+'/blender/');
    await page.waitForFunction(()=>document.querySelector('video').readyState>=1);
    assert.equal(await page.locator('#frame-counter').textContent(),'Frame 0 of 179');
    await page.locator('#next').click();
    await page.waitForFunction(()=>document.querySelector('#frame-counter').textContent==='Frame 1 of 179');
    const expected=await page.evaluate(()=>JSON.parse(document.querySelector('#scene-data').textContent).runs[0].frames[1].qpos[2]);
    assert.ok(Number.isFinite(expected));
    await page.locator('#timeline').evaluate(el=>{el.value='179';el.dispatchEvent(new Event('input',{bubbles:true}));});
    await page.waitForFunction(()=>document.querySelector('#frame-counter').textContent==='Frame 179 of 179');
    assert.equal(await page.locator('#left-contact').textContent(),'NO CONTACT RECORDED YET');
    assert.equal(await page.locator('#right-contact').textContent(),'CONTACT RECORDED');
    assert.equal(await page.locator('#blender-frame').textContent(),'180');
    assert.equal(await page.locator('#source-time').textContent(),'6.000');
    const expectedGap=await page.evaluate(()=>JSON.parse(document.querySelector('#scene-data').textContent).runs[0].frames[179].qpos[1].toFixed(3));
    assert.equal(await page.locator('#left-gap').textContent(),expectedGap);
  }finally{await page.close();}
});
test('Blender page works locally on mobile and downloads the editable project',async()=>{
  const page=await browser.newPage({viewport:{width:390,height:844}});
  try{
    await page.goto(pathToFileURL(resolve('docs/blender/index.html')).href);
    await page.waitForFunction(()=>document.querySelector('video').readyState>=1);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.locator('#next').focus();await page.keyboard.press('Enter');
    await page.waitForFunction(()=>document.querySelector('#blender-frame').textContent==='2');
    await page.goto(base+'/blender/');
    const pending=page.waitForEvent('download');
    await page.getByRole('link',{name:'Download .blend ↓'}).click();
    const download=await pending;
    assert.equal(download.suggestedFilename(),'replay.blend');
    const bytes=await readFile(await download.path());
    assert.deepEqual(bytes,await readFile(resolve('docs/blender/replay.blend')));
  }finally{await page.close();}
});
async function open(suffix=''){
  const page=await browser.newPage();
  await page.goto(base+'/studio/'+suffix);
  await page.waitForFunction(()=>document.querySelector('video').readyState>=1);
  return page;
}
test('shot seek, frame step, joint readout and scene boundary follow the recording',async()=>{
  const page=await open();
  try{
    await page.locator('.shot').nth(1).click();
    await page.waitForFunction(()=>document.querySelector('#frame-label').textContent.startsWith('Recorded frame 120 /'));
    await page.locator('#next').click();
    await page.waitForFunction(()=>document.querySelector('#frame-label').textContent.startsWith('Recorded frame 121 /'));
    await page.locator('#joint').selectOption({label:'Pitch'});
    const expected=await page.evaluate(()=>{
      const d=JSON.parse(document.querySelector('#reel-data').textContent);
      return d.scenes[0].frames[121].qpos[1].toFixed(3);
    });
    assert.equal(await page.locator('#measured').textContent(),expected);
    await page.locator('.shot').last().click();
    await page.waitForFunction(()=>document.querySelector('#mode').textContent.includes('Kinematic'));
    assert.equal(await page.locator('#joint option').count(),29);
    await page.locator('#timeline').evaluate(el=>{el.value='28';el.dispatchEvent(new Event('input',{bubbles:true}));});
    await page.waitForFunction(()=>document.querySelector('#joint').disabled);
    assert.equal(await page.locator('#measured').textContent(),'—');
  }finally{await page.close();}
});
test('deep links seek to a moment and share preserves the selected time',async()=>{
  const page=await open('#t=10.5');
  try{
    await page.waitForFunction(()=>Math.abs(document.querySelector('video').currentTime-10.5)<.01);
    assert.match(await page.locator('#frame-label').textContent(),/Recorded frame 255/);
    await page.locator('#share').click();
    assert.match(page.url(),/#t=10\.500$/);
  }finally{await page.close();}
});
test('plan download uses edited values without changing the recording',async()=>{
  const page=await open();
  try{
    await page.locator('#left').evaluate(el=>{el.value='-0.4';el.dispatchEvent(new Event('input',{bubbles:true}));});
    const pending=page.waitForEvent('download');
    await page.locator('#download-plan').click();
    const download=await pending;
    const plan=JSON.parse(await readFile(await download.path(),'utf8'));
    assert.equal(plan.shots[0].targets.Rotation,-.4);
    assert.deepEqual(plan.shots[3],{label:'Back to home.',home:true});
    assert.equal(plan.shots.length,4);
    assert.equal(await page.locator('video').evaluate(v=>v.currentTime),0);
  }finally{await page.close();}
});
test('mobile layout stays in viewport and shot buttons work with keyboard',async()=>{
  const page=await open();
  try{
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.locator('.shot').first().focus();
    await page.keyboard.press('Enter');
    await page.waitForFunction(()=>document.querySelector('#frame-label').textContent.startsWith('Recorded frame 0 /'));
  }finally{await page.close();}
});
test('the distributed page opens as a local file without a web server',async()=>{
  const page=await browser.newPage();
  try{
    await page.goto(pathToFileURL(resolve('docs/studio/index.html')).href+'#t=3');
    await page.waitForFunction(()=>document.querySelector('video').readyState>=1);
    await page.waitForFunction(()=>document.querySelector('#frame-label').textContent.startsWith('Recorded frame 30 /'));
    await page.locator('#share').click();
    assert.match(await page.locator('#status').textContent(),/only usable on your computer/);
  }finally{await page.close();}
});
test('caption text is displayed literally and cannot execute HTML',async()=>{
  const temp=await mkdtemp(join(tmpdir(),'robot-reel-xss-'));
  const page=await browser.newPage();
  try{
    let html=await readFile('docs/studio/index.html','utf8');
    const start=html.indexOf('<script type="application/json" id="reel-data">');
    const end=html.indexOf('</script>',start);
    const bodyStart=html.indexOf('>',start)+1;
    const data=JSON.parse(html.slice(bodyStart,end));
    const label='<img src=x onerror="window.injected=1">';
    data.scenes[0].frames[0].label=label;data.scenes[0].actions[0].label=label;
    html=html.slice(0,bodyStart)+JSON.stringify(data).replaceAll('<','\\u003c')+html.slice(end);
    html=html.replaceAll('src="../media/',`src="${base}/media/`);
    const file=join(temp,'index.html');await writeFile(file,html);
    await page.goto(pathToFileURL(file).href);
    await page.waitForFunction(()=>document.querySelector('video').readyState>=1);
    await page.locator('.shot').first().click();
    await page.waitForFunction(()=>document.querySelector('#caption').textContent.startsWith('<img'));
    assert.equal(await page.evaluate(()=>window.injected),undefined);
    assert.equal(await page.locator('#caption img').count(),0);
  }finally{await page.close();await rm(temp,{recursive:true,force:true});}
});
test('landing page indexes every published demo and copies the quick start',async()=>{
  const page=await browser.newPage();
  try{
    await page.goto(base+'/');
    const cards=page.locator('.card');
    assert.equal(await cards.count(),17);
    const hrefs=await cards.evaluateAll(links=>links.map(link=>link.getAttribute('href')));
    for(const href of hrefs){
      assert.ok(existsSync(resolve('docs',href,'index.html')),`${href} has no published page`);
    }
    assert.match(await page.locator('#commands').textContent(),/python3 -m robot_reel\.cli vla docs\/vla/);
    await page.locator('#copy').click();
    await page.waitForFunction(()=>['Copied','Select and copy'].includes(document.querySelector('#copy').textContent));
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
  }finally{await page.close();}
});
test('landing page offers a portable native inspector without loading a viewer in the background',async()=>{
  const page=await browser.newPage({viewport:{width:390,height:844},reducedMotion:'reduce'});
  const external=[],errors=[];
  page.on('request',request=>{if(!request.url().startsWith(base))external.push(request.url());});
  page.on('pageerror',error=>errors.push(error.message));
  try{
    await page.goto(base+'/#inspect');
    const link=new URL(await page.locator('#open-rerun').getAttribute('href'));
    assert.equal(link.origin,'https://app.rerun.io');
    assert.equal(link.pathname,'/version/0.37.2/');
    assert.equal(link.searchParams.get('url'),'https://noteflowai.github.io/robot-reel/rerun/seed-09.rrd');
    assert.match(await page.locator('#inspect .counts').textContent(),/6 embedded videos.*405 observations.*41 policy calls/);
    const download=page.waitForEvent('download');
    await page.locator('#download-rerun').click();
    assert.deepEqual(await readFile(await (await download).path()),await readFile('docs/rerun/seed-09.rrd'));
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    assert.deepEqual(external,[]);
    assert.deepEqual(errors,[]);
  }finally{await page.close();}
});
test('homepage tour opens the measured pair and links its full reproduction commands',async()=>{
  const page=await browser.newPage();
  try{
    const summary=JSON.parse(await readFile('docs/stress/summary.json','utf8'));
    const pair=summary.pairs.find(p=>p.seed===9&&p.condition==='dim');
    assert.equal(pair.reference_success,true);
    assert.equal(pair.condition_success,false);
    await page.goto(base+'/#tour');
    assert.match(await page.locator('#commands').textContent(),/python3 -m robot_reel\.cli stress docs\/stress/);
    await page.locator('#tour-inspect').click();
    assert.equal(new URL(page.url()).hash,'#inspect');
    await page.locator('#tour-reproduce').click();
    assert.equal(new URL(page.url()).hash,'#start');
    await page.locator('#tour-watch').click();
    await page.waitForFunction(()=>document.querySelector('#counter')?.textContent.startsWith('Sample 61 /'));
    const selected=new URLSearchParams(new URL(page.url()).hash.slice(1));
    assert.equal(Number(selected.get('frame')),pair.max_eef_frame);
    assert.equal(selected.get('seed'),'9');
    assert.equal(selected.get('condition'),'dim');
    assert.equal(await page.locator('#matrix button').count(),30);
  }finally{await page.close();}
});
test('homepage purpose filters preserve keyboard focus, share links and browser history',async()=>{
  const page=await browser.newPage({viewport:{width:390,height:844}});
  const visible=()=>page.locator('#demo-grid .card:visible').evaluateAll(cards=>cards.map(card=>card.getAttribute('href')).sort());
  try{
    await page.goto(base+'/#demos');
    const policies=page.locator('[data-filter="policies"]');
    await policies.focus();await page.keyboard.press('Enter');
    assert.deepEqual(await visible(),['compare/microduck/','libero-plus/','microduck-lab/','microduck/','stress/','vla/']);
    assert.equal(await policies.evaluate(el=>el===document.activeElement),true);
    assert.equal(await policies.getAttribute('aria-pressed'),'true');
    assert.equal(await page.locator('#demo-count').textContent(),'Showing 6 policy demos');
    assert.equal(new URL(page.url()).searchParams.get('category'),'policies');
    await page.locator('[data-filter="create"]').click();
    assert.deepEqual(await visible(),['blender/','cloth/','director/','newton/','remix/','scene-lab/','solver-lab/','studio/']);
    await page.goBack();
    await page.waitForFunction(()=>document.querySelector('[data-filter="policies"]').getAttribute('aria-pressed')==='true');
    assert.equal((await visible()).length,6);
    await page.goForward();await page.reload();
    assert.equal((await visible()).length,8);
    await page.locator('[data-filter="experiments"]').click();
    assert.deepEqual(await visible(),['braking/','chaos/','cloth/','compare/braking/','compare/microduck/','libero-plus/','microduck-lab/','newton/','scene-lab/','solver-lab/','stress/']);
    await page.locator('[data-filter="all"]').click();
    assert.equal((await visible()).length,17);
    assert.equal(new URL(page.url()).searchParams.has('category'),false);
    await page.goto(base+'/?category=__proto__#demos');
    assert.equal((await visible()).length,17);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  }finally{await page.close();}
});
test('homepage preview loads only on play and pauses when hidden or reduced motion is requested',async()=>{
  for(const reducedMotion of ['no-preference','reduce']){
    const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion});
    const requests=[],errors=[];
    page.on('request',request=>requests.push(request.url()));
    page.on('pageerror',error=>errors.push(error.message));
    try{
      await page.goto(base+'/',{waitUntil:'networkidle'});
      assert.equal(requests.some(url=>/\.(mp4|gif)(?:[?#]|$)/.test(url)),false);
      assert.equal(requests.some(url=>url.includes('app.rerun.io')),false);
      assert.equal(await page.locator('#hero-video').evaluate(v=>v.paused&&v.readyState===0),true);
      await page.locator('#preview-play').focus();await page.keyboard.press('Space');
      await page.waitForFunction(()=>document.querySelector('#hero-video').currentTime>.2);
      assert.equal(requests.some(url=>url.endsWith('/showcase/butterfly-preview.mp4')),true);
      assert.equal(await page.locator('#preview-play').getAttribute('aria-pressed'),'true');
      if(reducedMotion==='no-preference'){
        await page.emulateMedia({reducedMotion:'reduce'});
        await page.waitForFunction(()=>document.querySelector('#hero-video').paused);
        await page.locator('#preview-play').click();
        await page.waitForFunction(()=>!document.querySelector('#hero-video').paused);
      }
      await page.locator('#demos').scrollIntoViewIfNeeded();
      await page.waitForFunction(()=>document.querySelector('#hero-video').paused);
      assert.equal(await page.locator('#preview-play').getAttribute('aria-pressed'),'false');
      await page.locator('#hero-video').scrollIntoViewIfNeeded();
      assert.equal(await page.locator('#hero-video').evaluate(v=>v.paused),true);
      assert.deepEqual(errors,[]);
    }finally{await page.close();}
  }
});
test('homepage remains navigable without JavaScript and its filters work from file URLs',async()=>{
  const url=pathToFileURL(resolve('docs/index.html')).href;
  for(const target of [base+'/',url]){
    const page=await browser.newPage({javaScriptEnabled:false,viewport:{width:390,height:844}});
    try{
      await page.goto(target);
      assert.equal(await page.locator('#demo-grid .card:visible').count(),17);
      assert.equal(await page.locator('#filters').isVisible(),false);
      assert.equal(await page.locator('#copy').isVisible(),false);
      await page.locator('#tour-inspect').click();
      assert.equal(new URL(page.url()).hash,'#inspect');
      assert.match(await page.locator('#commands').textContent(),/stress docs\/stress/);
    }finally{await page.close();}
  }
  const page=await browser.newPage({viewport:{width:390,height:844}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  try{
    await page.goto(url+'?category=policies#demos');
    assert.equal(await page.locator('#demo-grid .card:visible').count(),6);
    await page.locator('[data-filter="create"]').click();
    assert.equal(await page.locator('#demo-grid .card:visible').count(),8);
    await page.locator('[data-filter="all"]').click();
    assert.equal(await page.locator('#demo-grid .card:visible').count(),17);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    assert.deepEqual(errors,[]);
  }finally{await page.close();}
});
test('homepage keeps an experiment entry when the optional preview cannot load',async()=>{
  const page=await browser.newPage();
  try{
    await page.route('**/butterfly-preview.mp4',route=>route.abort());
    await page.goto(base+'/');
    await page.locator('#preview-play').click();
    await page.waitForFunction(()=>document.querySelector('#preview-note').textContent.startsWith('Preview unavailable.'));
    await page.locator('.preview-actions a').click();
    assert.equal(new URL(page.url()).pathname,'/chaos/');
    await page.waitForFunction(()=>document.querySelector('#chaos-data')!==null);
  }finally{await page.close();}
});
test('Microduck page exposes policy data and a distinct download command',async()=>{
  const page=await browser.newPage();
  try{
    await page.goto(base+'/microduck/#t=5');
    await page.waitForFunction(()=>document.querySelector('#frame-label').textContent.startsWith('Recorded frame 90 /'));
    assert.equal(await page.locator('#joint option').count(),14);
    assert.match(await page.locator('#mode').textContent(),/Official ONNX policy/);
    assert.match(await page.locator('#quickstart').textContent(),/--pack microduck/);
    assert.equal(await page.locator('#media-notice').isVisible(),true);
    assert.equal(await page.locator('.shot').count(),3);
  }finally{await page.close();}
});
test('driving replay distinguishes contact outcomes and displays linear units',async()=>{
  const page=await browser.newPage();
  try{
    await page.goto(base+'/braking/#t=3');
    await page.waitForFunction(()=>document.querySelector('#scene').textContent==='LATE BRAKE');
    assert.match(await page.locator('#mode').textContent(),/Contact recorded/);
    assert.equal(await page.locator('#unit').textContent(),'MEASURED / M/S');
    await page.locator('.shot').last().click();
    await page.waitForFunction(()=>document.querySelector('#scene').textContent==='EARLY BRAKE');
    assert.match(await page.locator('#mode').textContent(),/No contact/);
    await page.locator('#joint').selectOption({label:'gap'});
    assert.equal(await page.locator('#unit').textContent(),'MEASURED / M');
  }finally{await page.close();}
});
test('comparison seeks both videos, steps frames, reads channels and shares time',async()=>{
  const page=await browser.newPage();
  try{
    await page.goto(base+'/compare/microduck/#t=5');
    await page.waitForFunction(()=>[...document.querySelectorAll('video')].every(v=>Math.abs(v.currentTime-5)<.001));
    assert.match(await page.locator('#status').textContent(),/Frame 150/);
    await page.locator('#next').click();
    await page.waitForFunction(()=>[...document.querySelectorAll('video')].every(v=>Math.abs(v.currentTime-151/30)<.001));
    await page.locator('#joint').selectOption('3');
    const expected=await page.evaluate(()=>{const d=JSON.parse(document.querySelector('#comparison-data').textContent);return d.traces[1].frames[151].qpos[3].toFixed(3);});
    assert.ok((await page.locator('#reading-1').textContent()).includes(expected));
    await page.locator('#share').click();assert.ok(page.url().endsWith('#t=5.033'));
    await page.locator('#play').click();await page.waitForFunction(()=>document.querySelector('#left').currentTime>5.3);await page.locator('#play').click();
    const times=await page.locator('video').evaluateAll(v=>v.map(x=>x.currentTime));
    assert.ok(times[0]>5.1);assert.ok(Math.abs(times[0]-times[1])<.001);
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  }finally{await page.close();}
});
test('braking comparison exposes contact evidence and runs from a local file',async()=>{
  const page=await browser.newPage();
  try{
    await page.goto(pathToFileURL(resolve('docs/compare/braking/index.html')).href+'#t=4');
    await page.waitForFunction(()=>document.querySelector('#left').currentTime===4);
    assert.match(await page.locator('#metrics-0').textContent(),/None recorded/);
    assert.match(await page.locator('#metrics-1').textContent(),/Recorded/);
    assert.equal(await page.locator('#joint option').count(),3);
  }finally{await page.close();}
});
