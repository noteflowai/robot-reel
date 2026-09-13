// Exercise the installed wheel's actual cloth archive with all HTTP blocked.
const assert=require('node:assert/strict');
const {readFile}=require('node:fs/promises');
const {resolve}=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');

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
        await page.locator('#share').click();await page.reload();
        assert.equal(await page.locator('#counter').textContent(),'Sample 30 / 120');
        assert.equal(await page.locator('#overlay').getAttribute('aria-pressed'),'true');
        await page.locator('#start').click();
        assert.equal(await page.locator('#distance').textContent(),'0.000');
        await page.locator('#play').click();
        await page.waitForFunction(()=>Number(document.querySelector('#timeline').value)>=3);
        await page.locator('#play').click();
        const download=page.waitForEvent('download');
        await page.getByRole('link',{name:'OpenUSD scene ↓',exact:true}).click();
        assert.deepEqual(await readFile(await (await download).path()),await readFile(resolve(lab,'scene.usdc')));
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
        assert.deepEqual(network,[]);assert.deepEqual(errors,[]);
        results.push({width,height,vertex_samples:trace.summary.vertex_samples,played:true,
          binary_payload_matches:true,shared_sample_restored:true,usd_download_matches:true,network_requests:0});
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
