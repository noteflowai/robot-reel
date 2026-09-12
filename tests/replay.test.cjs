const {test, before, after} = require('node:test');
const assert = require('node:assert/strict');
const {createServer} = require('node:http');
const {readFile, writeFile, mkdtemp, rm} = require('node:fs/promises');
const {tmpdir} = require('node:os');
const {join, resolve, extname} = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require('playwright');
let browser, server, base;
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
    await page.waitForFunction(()=>[...document.querySelectorAll('video')].every(v=>v.readyState>=1));
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
test('Microduck landing page exposes policy data and a distinct download command',async()=>{
  const page=await browser.newPage();
  try{
    await page.goto(base+'/#t=5');
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
