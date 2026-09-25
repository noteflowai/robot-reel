'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
const {chromium}=require('playwright');
(async()=>{
 const root=path.resolve('docs/model-review'),browser=await chromium.launch({headless:true}),errors=[];
 try{
  const data=JSON.parse(await fs.readFile(path.join(root,'review.json'),'utf8'));
  await fs.mkdir('artifacts/model-review-browser',{recursive:true});
  for(const width of [1440,390,320]){
   const page=await browser.newPage({viewport:{width,height:1100},reducedMotion:'reduce'}),requests=[];
   page.on('pageerror',error=>errors.push(String(error)));page.on('request',request=>requests.push(request.url()));
   await page.goto('file://'+path.join(root,'index.html'));
   await page.locator('#record-outcome').filter({hasText:'success'}).waitFor();
   assert.equal(await page.locator('#episodes button').count(),3);
   assert(!requests.some(url=>url.endsWith('.mp4')),'Video loaded before play');
   for(const episode of data.episodes){
    await page.locator(`[data-episode="${episode.id}"]`).click();
    assert.equal(await page.locator('#record-actions').innerText(),String(episode.record.actions));
    for(const mode of ['images-only','with-record']){
     await page.locator(`[data-mode="${mode}"]`).click();
     assert.equal(await page.locator(`[data-mode="${mode}"]`).getAttribute('aria-pressed'),'true');
     assert.equal(JSON.parse(await page.locator('#raw').textContent()).text,episode.reviews[mode].record.text);
     assert.equal(await page.locator('#checks tr').count(),episode.reviews[mode].review.checks?.length||1);
    }
   }
   await page.locator('[data-episode="episode-b"]').click();
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.locator('#main-video').evaluate(video=>video.play());
   await page.waitForFunction(()=>document.querySelector('#main-video').currentTime>0.2);
   await page.locator('#main-video').evaluate(video=>video.pause());
   await page.locator('#main-video').evaluate(video=>{video.currentTime=2});
   await page.waitForFunction(()=>Math.abs(document.querySelector('#main-video').currentTime-document.querySelector('#wrist-video').currentTime)<0.2);
   await page.screenshot({path:`artifacts/model-review-browser/${width}.png`,fullPage:true});
   assert(requests.every(url=>url.startsWith('file:')),'Unexpected network request');
   await page.close();
  }
  const nojs=await browser.newPage({javaScriptEnabled:false});await nojs.goto('file://'+path.join(root,'index.html'));assert(await nojs.locator('noscript').isVisible());await nojs.close();
  assert.deepEqual(errors,[]);console.log('Model review passed: original responses, modes, synchronized playback, desktop/mobile/320px, file://, no network, no-JS links.');
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
