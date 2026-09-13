// Exercise the actual archive exported by the installed wheel, with network blocked.
const assert=require('node:assert/strict');
const {readFile}=require('node:fs/promises');
const {resolve}=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');

async function check(lab,reviewFile){
  const review=JSON.parse(await readFile(reviewFile,'utf8'));
  const browser=await chromium.launch();
  const results=[];
  try{
    for(const [width,height] of [[1440,1000],[390,844]]){
      const page=await browser.newPage({viewport:{width,height},reducedMotion:'reduce'});
      const errors=[],network=[];
      page.on('pageerror',e=>errors.push(e.message));
      await page.route(/^https?:/,route=>{network.push(route.request().url());return route.abort();});
      try{
        await page.goto(pathToFileURL(resolve(lab,'index.html')).href);
        assert.equal(await page.locator('#matrix button').count(),30);
        assert.equal(await page.locator('#zip').isVisible(),false);
        await page.locator('#review-file').setInputFiles(reviewFile);
        await page.waitForFunction(()=>document.querySelector('#review-status').textContent.startsWith('Recorded facts match'));
        assert.equal(await page.locator('#seed').inputValue(),'9');
        assert.equal(await page.locator('#condition').inputValue(),'dim');
        assert.equal(await page.locator('#timeline').inputValue(),'100');
        assert.equal(await page.locator('#wrist').getAttribute('aria-pressed'),'true');
        assert.match(await page.locator('#left-clock').textContent(),/SOURCE 082.*HELD FINAL/);
        assert.equal(await page.locator('#left-inference').textContent(),'Terminal observation · no action');
        await page.waitForFunction(()=>[...document.querySelectorAll('video')].every(v=>v.readyState>=2&&!v.seeking));
        await page.locator('#play').click();
        await page.waitForFunction(()=>Number(document.querySelector('#timeline').value)>=103);
        await page.locator('#play').click();
        await page.locator('#review-file').setInputFiles(reviewFile);
        await page.waitForFunction(()=>Number(document.querySelector('#timeline').value)===100);
        const pending=page.waitForEvent('download');await page.locator('#review-json').click();
        const download=await pending;
        assert.deepEqual(JSON.parse(await readFile(await download.path(),'utf8')),review);
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
        assert.deepEqual(network,[]);assert.deepEqual(errors,[]);
        results.push({width,height,all_trials:30,review_matches:true,video_played:true,network_requests:0});
      }finally{await page.close();}
    }
  }finally{await browser.close();}
  return results;
}

if(require.main===module){
  const [lab,review]=process.argv.slice(2);
  if(!lab||!review){console.error('Usage: node scripts/check_offline_release.cjs LAB_FOLDER REVIEW_JSON');process.exitCode=1;}
  else check(resolve(lab),resolve(review)).then(r=>console.log(JSON.stringify(r,null,2))).catch(e=>{console.error(e);process.exitCode=1;});
}
module.exports={check};
