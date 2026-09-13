// Exercise the installed wheel's actual cloth archive with all HTTP blocked.
const assert=require('node:assert/strict');
const {readFile}=require('node:fs/promises');
const {resolve}=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');
const {createHash}=require('node:crypto');

async function check(lab){
  const trace=JSON.parse(await readFile(resolve(lab,'trace.json'),'utf8'));
  const positions=await readFile(resolve(lab,'positions.f32'));
  const vertex=(f,c,i)=>Array.from({length:3},(_,a)=>positions.readFloatLE(4*(((f*3+c)*117+i)*3+a)));
  const measured=f=>Math.sqrt(Array.from({length:117},(_,i)=>{
    const p=vertex(f,2,i),reference=vertex(f,0,i);
    return p.reduce((sum,v,a)=>sum+(v-reference[a])**2,0);
  }).reduce((a,b)=>a+b,0)/117);
  const browser=await chromium.launch(),results=[];
  try{
    for(const [width,height] of [[1440,1000],[390,844]]){
      const page=await browser.newPage({viewport:{width,height},reducedMotion:'reduce'});
      const errors=[],network=[];page.on('pageerror',e=>errors.push(e.message));
      await page.route(/^https?:/,route=>{network.push(route.request().url());return route.abort();});
      try{
        await page.goto(pathToFileURL(resolve(lab,'index.html')).href+'#case=2&frame=29&view=overlay');
        const payload=JSON.parse(await page.locator('#cloth-data').textContent());
        assert.deepEqual(payload.trace,trace);
        assert.deepEqual(Buffer.from(payload.positions_base64,'base64'),positions);
        assert.equal(await page.locator('#distance').textContent(),measured(29).toFixed(3));
        assert.equal(await page.locator('#download-archive').isVisible(),false);
        await page.locator('#next').click();
        assert.equal(await page.locator('#counter').textContent(),'Sample 30 / 120');
        assert.equal(await page.locator('#distance').textContent(),measured(30).toFixed(3));
        await page.locator('#rotate-left').click();
        const image=await page.locator('#scene').evaluate(c=>c.toDataURL());
        await page.locator('#share').click();await page.reload();
        assert.equal(await page.locator('#counter').textContent(),'Sample 30 / 120');
        assert.equal(await page.locator('#overlay').getAttribute('aria-pressed'),'true');
        assert.equal(await page.locator('#scene').evaluate(c=>c.toDataURL()),image);
        const recordDownload=page.waitForEvent('download');await page.locator('#sample-json').click();
        const record=JSON.parse(await readFile(await (await recordDownload).path()));
        assert.equal(record.schema,'robot-reel-cloth-sample-1');
        assert.equal(record.sample,30);assert.equal(record.time_s,1);assert.equal(record.blender_frame,31);
        assert.ok(Math.abs(record.metrics.rms_separation_m-measured(30))<1e-12);
        assert.equal(record.source.positions_sha256,createHash('sha256').update(positions).digest('hex'));
        assert.ok(Math.abs(record.presentation.yaw_rad+.68)<1e-12);
        const figureDownload=page.waitForEvent('download');await page.locator('#figure').click();
        const png=await readFile(await (await figureDownload).path());
        assert.deepEqual([...png.subarray(0,8)],[137,80,78,71,13,10,26,10]);
        assert.equal(png.readUInt32BE(16),1920);assert.equal(png.readUInt32BE(20),1080);
        await page.locator('#start').click();
        assert.equal(await page.locator('#distance').textContent(),'0.000');
        await page.locator('#play').click();
        await page.waitForFunction(()=>Number(document.querySelector('#timeline').value)>=3);
        await page.locator('#play').click();
        await page.locator('#sample-file').setInputFiles({name:'sample.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(record))});
        await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Verified sample 30'));
        assert.equal(await page.locator('#timeline').inputValue(),'30');
        assert.equal(await page.locator('#scene').evaluate(c=>c.toDataURL()),image);
        const changed=structuredClone(record);changed.source.positions_sha256='0'.repeat(64);
        await page.locator('#sample-file').setInputFiles({name:'changed.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(changed))});
        await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Could not open sample:'));
        assert.equal(await page.locator('#scene').evaluate(c=>c.toDataURL()),image);
        const download=page.waitForEvent('download');
        await page.getByRole('link',{name:'OpenUSD scene ↓',exact:true}).click();
        assert.deepEqual(await readFile(await (await download).path()),await readFile(resolve(lab,'scene.usdc')));
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
        assert.deepEqual(network,[]);assert.deepEqual(errors,[]);
        results.push({width,height,vertex_samples:trace.summary.vertex_samples,played:true,
          binary_payload_matches:true,shared_sample_restored:true,shared_camera_restored:true,
          figure_png:[1920,1080],sample_json_matches:true,sample_import_restored:true,
          changed_sample_rejected:true,usd_download_matches:true,network_requests:0});
      }finally{await page.close();}
    }
  }finally{await browser.close();}
  return results;
}

if(require.main===module){
  const [lab]=process.argv.slice(2);
  if(!lab){console.error('Usage: node scripts/check_cloth_release.cjs LAB_FOLDER');process.exitCode=1;}
  else check(resolve(lab)).then(r=>console.log(JSON.stringify(r,null,2))).catch(e=>{console.error(e);process.exitCode=1;});
}
module.exports={check};
