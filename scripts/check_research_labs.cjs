// Exercise real media clocks, lazy 3D rendering, downloads and narrow viewports.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const fs=require('node:fs/promises');
const path=require('node:path');
const readline=require('node:readline');
const {chromium}=require('playwright');

async function main(){
 const root=path.resolve(process.argv[2]||'docs');
 const output=path.resolve(process.argv[3]||'artifacts/research-browser');
 await fs.mkdir(output,{recursive:true});
 const server=spawn('python3',['-u','-m','http.server','0','--bind','127.0.0.1','--directory',root],{stdio:['ignore','pipe','ignore']});
 let browser;
 try{
  const port=await new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>reject(new Error('local HTTP server did not start')),10000);
   const lines=readline.createInterface({input:server.stdout});
   lines.on('line',line=>{const match=line.match(/port (\d+)/);if(match){clearTimeout(timer);resolve(Number(match[1]));}});
   server.once('error',reject);server.once('exit',code=>reject(new Error(`HTTP server exited ${code}`)));
  });
  const base=`http://127.0.0.1:${port}`;
  browser=await chromium.launch({args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  const results=[];
  for(const width of [1440,390,320]){
   const page=await browser.newPage({viewport:{width,height:1100},reducedMotion:'reduce'}),errors=[];
   page.on('pageerror',error=>errors.push(error.message));
   await page.goto(`${base}/libero-plus/`);
   await page.waitForFunction(()=>!document.getElementById('play').disabled);
   await page.locator('#reference-end').click();
   await page.waitForFunction(()=>Math.abs(document.getElementById('reference').currentTime-3.85)<.02);
   assert.match(await page.locator('#reference-clock').textContent(),/holding sample 77/);
   await page.locator('#condition').selectOption('light-conditions');
   await page.locator('#end').click();
   await page.waitForFunction(()=>Math.abs(document.getElementById('challenge').currentTime-4.35)<.02);
   assert.equal(await page.locator('#sample').getAttribute('max'),'87');
   assert.equal(await page.locator('#next').isDisabled(),true);
   await page.locator('#previous').click();
   assert.equal(await page.locator('#sample').inputValue(),'86');
   const hash=await page.evaluate(()=>location.hash);
   await page.reload();await page.waitForFunction(()=>!document.getElementById('play').disabled);
   assert.equal(await page.locator('#sample').inputValue(),'86');
   assert.equal(await page.locator('#condition').inputValue(),'light-conditions');
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   assert.deepEqual(errors,[]);
   await page.screenshot({path:path.join(output,`libero-plus-${width}.png`),fullPage:true});
   results.push({page:'libero-plus',width,hash,errors});await page.close();
  }
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[],requests=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
  page.on('request',request=>requests.push(request.url()));
  await page.goto(`${base}/scene-lab/`);
  assert.equal(requests.some(url=>url.endsWith('.glb')||url.includes('/vendor/')),false);
  await page.locator('#load').click();
  await page.waitForFunction(()=>document.getElementById('status').textContent.startsWith('Showing'),null,{timeout:60000});
  await page.screenshot({path:path.join(output,'scene-mesh.png'),fullPage:true});
  await page.locator('input[value=splats]').check();
  await page.waitForFunction(()=>document.getElementById('status').textContent.includes('Showing original surface Gaussians'),null,{timeout:60000});
  // A successful button transition alone is insufficient: require real sorted
  // splat geometry in the renderer before taking the screenshot.
  assert.equal(await page.evaluate(()=>app.cache.get('baseline').splats.splats.getNumSplats()),25000);
  assert.ok(await page.evaluate(()=>app.spark.display.numSplats)>0);
  await page.screenshot({path:path.join(output,'scene-splats.png'),fullPage:true});
  await page.locator('input[value=collision]').check();
  await page.locator('input[value=edited]').check();
  await page.waitForFunction(()=>document.getElementById('status').textContent.includes('Showing edited collision proxy'));
  assert.equal(await page.evaluate(()=>app.cache.get('edited').collision.visible),true);
  const pending=page.waitForEvent('download');await page.locator('#recipe button').click();
  const recipe=JSON.parse(await fs.readFile(await (await pending).path(),'utf8'));
  assert.deepEqual(recipe,{schema:'robot-reel.scene-edit.v1',terrain_z_scale:1.4,sun_azimuth_degrees:310,sun_energy:3});
  for(const width of [390,320]){
   await page.setViewportSize({width,height:1000});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   await page.screenshot({path:path.join(output,`scene-${width}.png`),fullPage:true});
  }
  assert.deepEqual(errors,[]);
  results.push({page:'scene-lab',widths:[1440,390,320],sortedSplats:25000,errors});
  await fs.writeFile(path.join(output,'checks.json'),JSON.stringify(results,null,2)+'\n');
  console.log(JSON.stringify(results));
 }finally{await browser?.close();server.kill('SIGTERM');}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
