// Exercise the offline Factory Twin viewer and check its displayed values against lab.json.
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');

async function main(){
 const root=path.resolve(process.argv[2]||'docs/factory-twin');
 const lab=JSON.parse(await fs.readFile(path.join(root,'lab.json'),'utf8'));
 const N=lab.config.samples,url=pathToFileURL(path.join(root,'index.html')).href;
 const browser=await chromium.launch();
 try{
  for(const width of [1440,390,320]){
   const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'}),errors=[],requests=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.route(/^https?:/,route=>{requests.push(route.request().url());return route.abort();});
   await page.addInitScript(()=>Object.defineProperty(navigator,'clipboard',{value:{writeText:()=>Promise.reject(new Error('clipboard disabled'))}}));
   await page.goto(url+'#mode=closed&k=400');
   assert.equal(await page.locator('#sample').inputValue(),'400');
   const closed=lab.runs.closed,shadow=lab.runs.shadow;
   assert.equal(await page.locator('#k-good').textContent(),String(closed.plant.good[400]));
   assert.match(await page.locator('#k-good-note').textContent(),new RegExp(`Shadow run at this time: ${shadow.plant.good[400]} `));
   assert.equal(await page.locator('#seeds tr').count(),lab.seeds.seeds.length);
   const logRows=await page.locator('#log tr').count();assert.equal(logRows,closed.decisions.length);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   // Mode toggle keeps the sample and swaps every panel to the shadow record.
   await page.locator('[data-mode=shadow]').click();
   assert.equal(await page.locator('[data-mode=shadow]').getAttribute('aria-pressed'),'true');
   assert.equal(await page.locator('#k-good').textContent(),String(shadow.plant.good[400]));
   assert.equal(await page.locator('#log tr').count(),shadow.decisions.length);
   assert.match(await page.locator('#loop-act').textContent(),/logged, none applied/);
   // Decision navigation lands exactly on a recorded decision time.
   await page.locator('#next-decision').click();
   const k=Number(await page.locator('#sample').inputValue());
   assert.ok(shadow.decisions.some(d=>d.kind!=='plan'&&d.t===k*lab.config.sample_s),`sample ${k} is not a decision`);
   await page.locator('#next').click();assert.equal(await page.locator('#sample').inputValue(),String(k+1));
   await page.locator('#prev').click();assert.equal(await page.locator('#sample').inputValue(),String(k));
   // Log jump.
   await page.locator('#only-actions').check();
   const commands=shadow.decisions.filter(d=>d.actuated!=null||d.kind==='alarm');
   assert.equal(await page.locator('#log tr').count(),commands.length);
   await page.locator('#log button').first().click();
   assert.equal(await page.locator('#sample').inputValue(),String(commands[0].t/lab.config.sample_s));
   // Share link falls back to showing the URL when the clipboard is unavailable, and restores state.
   await page.locator('#share').click();
   const shared=await page.evaluate(()=>location.hash);
   assert.equal(shared,`#mode=shadow&k=${commands[0].t/lab.config.sample_s}`);
   await page.reload();
   assert.equal(await page.locator('[data-mode=shadow]').getAttribute('aria-pressed'),'true');
   // CSV contains every sample of the selected mode.
   const pending=page.waitForEvent('download');await page.locator('#csv').click();
   const csv=(await fs.readFile(await (await pending).path(),'utf8')).trim().split('\n');
   assert.equal(csv.length,N+1);
   for(const i of [0,400,N-1]){const c=csv[i+1].split(',');
    assert.equal(Number(c[3]),shadow.plant.good[i]);assert.equal(Number(c[6]),shadow.plant.wear[i]);assert.equal(Number(c[7]),shadow.twin.wear[i]);}
   // Playback advances and pauses.
   await page.locator('[data-mode=closed]').click();await page.locator('#sample').fill('0');
   await page.locator('#play').click();
   await page.waitForFunction(()=>Number(document.querySelector('#sample').value)>=3);
   await page.locator('#play').click();
   const paused=await page.locator('#sample').inputValue();await page.waitForTimeout(150);
   assert.equal(await page.locator('#sample').inputValue(),paused);
   // Orbit and camera presets redraw without errors.
   const box=await page.locator('#scene').boundingBox();
   await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();
   await page.mouse.move(box.x+box.width/2+80,box.y+box.height/2+20);await page.mouse.up();
   for(const view of ['hall','cnc','energy','campus'])await page.locator(`[data-view=${view}]`).click();
   await page.locator('#ghosts').click();assert.equal(await page.locator('#ghosts').getAttribute('aria-pressed'),'false');
   if(process.env.FACTORY_SCREENSHOTS){await fs.mkdir(process.env.FACTORY_SCREENSHOTS,{recursive:true});
    await page.screenshot({path:path.join(process.env.FACTORY_SCREENSHOTS,`factory-twin-${width}.png`),fullPage:true});}
   assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
   await page.close();
  }
  console.log('Factory Twin: 1440/390/320px offline replay, both loop modes, decision navigation, share links and CSV samples passed.');
 }finally{await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
