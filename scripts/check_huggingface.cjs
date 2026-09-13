// Exercise the shipped Space, including a cross-origin host with clipboard access denied.
const assert=require('node:assert/strict');
const {createServer}=require('node:http');
const {readFile}=require('node:fs/promises');
const {resolve,extname}=require('node:path');
const {chromium}=require('playwright');

async function check(directory){
 const root=resolve(directory);
 const server=createServer(async(req,res)=>{
  const url=new URL(req.url,'http://localhost');
  if(url.pathname==='/embed'){
   res.setHeader('Content-Type','text/html');
   res.end(`<!doctype html><style>body{margin:0}iframe{width:100%;height:100vh;border:0}</style><iframe title="Robot Reel Space" src="http://127.0.0.1:${server.address().port}/" allow="clipboard-read 'none'; clipboard-write 'none'" sandbox="allow-scripts allow-same-origin allow-downloads allow-popups allow-popups-to-escape-sandbox"></iframe>`);return;
  }
  const path=resolve(root,'.'+decodeURIComponent(url.pathname.endsWith('/')?url.pathname+'index.html':url.pathname));
  if(!path.startsWith(root+'/')){res.writeHead(403).end();return;}
  try{
   const bytes=await readFile(path),mime={'.html':'text/html','.mp4':'video/mp4','.png':'image/png','.json':'application/json'};
   res.setHeader('Content-Type',mime[extname(path)]||'application/octet-stream');
   const range=/^bytes=(\d+)-(\d*)$/.exec(req.headers.range||'');
   if(range){const start=Number(range[1]),end=Math.min(bytes.length-1,range[2]?Number(range[2]):bytes.length-1);
    res.writeHead(206,{'Accept-Ranges':'bytes','Content-Range':`bytes ${start}-${end}/${bytes.length}`,'Content-Length':end-start+1});res.end(bytes.subarray(start,end+1));
   }else res.end(bytes);
  }catch{res.writeHead(404).end();}
 });
 await new Promise(r=>server.listen(0,'0.0.0.0',r));
 const browser=await chromium.launch(),rows=[];
 try{
  for(const width of [1440,390]){
   const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'}),errors=[],missing=[],external=[];
   page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.status()>=400)missing.push(r.url());});
   await page.route(/^https?:/,route=>{const host=new URL(route.request().url()).hostname;if(!['localhost','127.0.0.1'].includes(host)){external.push(route.request().url());return route.abort();}return route.continue();});
   await page.goto(`http://localhost:${server.address().port}/embed`);
   const frame=page.frameLocator('iframe');
   await frame.locator('#lab-cloth').waitFor();
   assert.equal(await frame.locator('.card').count(),3);
   const homeText=await frame.locator('body').innerText();
   assert.ok(homeText.includes('0.05° apart.'));
   assert.ok(homeText.includes('中文'));
   assert.ok(!homeText.includes('\uFFFD'));
   const home=page.frames().find(f=>f.url().includes('127.0.0.1'));
   assert.equal(await home.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   assert.equal(await frame.locator('video').evaluate(v=>v.paused&&v.preload==='none'),true);
   for(const [lab,fragment] of [['cloth','frame=61&case=1&view=overlay&yaw=-0.9'],['stress','seed=9&condition=dim&frame=61&camera=wrist'],['chaos','frame=61&world=4&view=overlay']]){
    const inside=page.frames().find(f=>f.url().includes('127.0.0.1'));
    await inside.goto(`http://127.0.0.1:${server.address().port}/${lab}/index.html#${fragment}`);
    if(lab==='stress')await inside.waitForFunction(()=>[...document.querySelectorAll('video')].every(v=>v.readyState>=2&&!v.seeking));
    await frame.locator('#share').click();
    const url=await frame.locator('#share-url').inputValue();
    assert.ok(url.startsWith(`http://127.0.0.1:${server.address().port}/${lab}/index.html#`));
    assert.equal(new URL(url).searchParams.size,0);
    assert.equal(new URLSearchParams(new URL(url).hash.slice(1)).get('frame'),'61');
    assert.equal(await frame.locator('#share-open').getAttribute('href'),url);
    assert.equal(await frame.locator('#share-open').getAttribute('target'),'_blank');
    assert.equal(await inside.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    if(lab==='cloth'){
     const pending=page.waitForEvent('download');await frame.locator('#sample-json').click();const bytes=await readFile(await (await pending).path());
     assert.equal(JSON.parse(bytes).sample,61);await frame.locator('#start').click();
     await frame.locator('#sample-file').setInputFiles({name:'sample.json',mimeType:'application/json',buffer:bytes});
     await inside.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Verified sample 61'));
     const png=page.waitForEvent('download');await frame.locator('#figure').click();const image=await readFile(await (await png).path());
     assert.equal(image.readUInt32BE(16),1920);assert.equal(image.readUInt32BE(20),1080);
    }
   }
   assert.deepEqual(errors,[]);assert.deepEqual(missing,[]);assert.deepEqual(external,[]);
   rows.push({width,labs:3,cross_origin_embed:true,clipboard_denied:true,share_links:true,
    cloth_figure_and_sample:true,missing_assets:0,external_runtime_requests:0});
   await page.close();
  }
 }finally{await browser.close();await new Promise(r=>server.close(r));}
 return rows;
}
if(require.main===module)check(process.argv[2]).then(r=>console.log(JSON.stringify(r,null,2))).catch(e=>{console.error(e);process.exitCode=1;});
module.exports={check};
