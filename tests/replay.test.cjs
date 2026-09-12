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
