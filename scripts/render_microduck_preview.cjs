// Capture the actual recorded frame and its body-fixed schematic, without a server.
const {chromium}=require('playwright');
const {resolve}=require('node:path');
const {pathToFileURL}=require('node:url');
(async()=>{
 const root=resolve(process.argv[2]||'docs/microduck-lab'),browser=await chromium.launch();
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100},deviceScaleFactor:1,reducedMotion:'reduce'});
  await page.goto(pathToFileURL(root+'/index.html').href+'#run=right&frame=120&joint=3');
  await page.waitForFunction(()=>{const v=document.querySelector('video');return v.readyState>=2&&!v.seeking;});
  await page.locator('.workspace').screenshot({path:root+'/poster.png'});
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
