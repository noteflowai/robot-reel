// Exercise the actual offline viewer and independently check its downloads.
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');

async function main(){
 const root=path.resolve(process.argv[2]||'docs/solver-lab');
 const lab=JSON.parse(await fs.readFile(path.join(root,'lab.json'),'utf8'));
 const browser=await chromium.launch();
 try{
  for(const width of [1440,390,320]){
   const page=await browser.newPage({viewport:{width,height:width===1440?1300:1000},reducedMotion:'reduce'}),errors=[],requests=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.route(/^https?:/,route=>{requests.push(route.request().url());return route.abort();});
   await page.addInitScript(()=>Object.defineProperty(navigator,'clipboard',{value:{writeText:()=>Promise.reject(new Error('clipboard disabled'))}}));
   await page.goto(pathToFileURL(path.join(root,'index.html')).href);
   assert.equal(await page.locator('#runs tr').count(),6);
   assert.equal(await page.locator('#sample').inputValue(),'60');
   assert.equal(await page.locator('#position-error').textContent(),'32.700 cm');
   assert.equal(await page.locator('#next').isDisabled(),true);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   await page.locator('input[name=engine][value=newton]').check();
   await page.locator('input[name=substeps][value="16"]').check();
   assert.equal(await page.locator('#position-error').textContent(),'2.046 cm');
   await page.locator('#sample').fill('31');
   const run=lab.runs.find(r=>r.id==='newton-16'),f=run.frames[31],t=31/30;
   const error=Math.hypot(f.position_m[0]-2*t,f.position_m[1],f.position_m[2]-(1+10*t-4.905*t*t));
   assert.equal(await page.locator('#position-error').textContent(),`${(error*100).toFixed(3)} cm`);
   await page.locator('#next').click();assert.equal(await page.locator('#sample').inputValue(),'32');
   await page.locator('#previous').click();assert.equal(await page.locator('#sample').inputValue(),'31');
   await page.locator('#share').click();
   const link=await page.locator('#share-url').inputValue(),hash=new URLSearchParams(new URL(link).hash.slice(1));
   assert.equal(hash.get('engine'),'newton');assert.equal(hash.get('substeps'),'16');assert.equal(hash.get('sample'),'31');
   assert.equal(await page.locator('#share-open').getAttribute('href'),link);
   assert.equal(await page.locator('#share-url').evaluate(e=>e===document.activeElement),true);
   const pending=page.waitForEvent('download');await page.locator('#csv').click();
   const csv=(await fs.readFile(await (await pending).path(),'utf8')).trim().split('\n');
   assert.equal(csv.length,367);
   for(const [i,row] of csv.slice(1).entries()){
    const r=lab.runs[Math.floor(i/61)],f=r.frames[i%61],columns=row.split(',');
    assert.deepEqual(columns.slice(0,2),[r.engine,r.engine_version]);
    assert.deepEqual(columns.slice(3,11).map(Number),[f.sample,f.time_s,...f.position_m,...f.velocity_m_s]);
   }
   const pendingJSON=page.waitForEvent('download');await page.locator('#json').click();
   assert.deepEqual(JSON.parse(await fs.readFile(await (await pendingJSON).path(),'utf8')),lab);
   await page.reload();assert.equal(await page.locator('#sample').inputValue(),'31');
   assert.equal(await page.locator('input[name=engine]:checked').inputValue(),'newton');
   await page.locator('#peak').click();assert.equal(await page.locator('#sample').inputValue(),'60');
   await page.locator('#play').click();
   await page.waitForFunction(()=>{const n=Number(document.querySelector('#sample').value);return n>=3&&n<60;});
   await page.locator('#play').click();
   const paused=await page.locator('#sample').inputValue();
   await page.waitForTimeout(100);assert.equal(await page.locator('#sample').inputValue(),paused);
   await page.goto(pathToFileURL(path.join(root,'index.html')).href+'#engine=missing&sample=900');
   assert.match(await page.locator('#status').textContent(),/Unrecognized/);
   await page.locator('#reset').click();
   assert.equal(await page.locator('#sample').inputValue(),'60');
   if(process.env.SOLVER_SCREENSHOTS){
    await fs.mkdir(process.env.SOLVER_SCREENSHOTS,{recursive:true});
    await page.evaluate(()=>scrollTo(0,0));
    await page.screenshot({path:path.join(process.env.SOLVER_SCREENSHOTS,`solver-${width}.png`),fullPage:true});
    if(width===1440)await page.screenshot({path:path.join(process.env.SOLVER_SCREENSHOTS,'poster.png'),clip:{x:0,y:0,width:1440,height:1300}});
   }
   assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
   await page.close();
  }
  console.log('Solver Lab: 1440/390/320px offline replay, clocks, all CSV/JSON samples, shared views and clipboard recovery passed.');
 }finally{await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
