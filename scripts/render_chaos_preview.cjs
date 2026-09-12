// Capture real source samples in the browser, with no interpolation or resimulation.
const {chromium}=require('playwright');
const {mkdir,writeFile}=require('node:fs/promises');
const {resolve,join}=require('node:path');
const {pathToFileURL}=require('node:url');
(async()=>{
 const source=resolve(process.argv[2]||'docs/chaos'),output=resolve(process.argv[3]||'artifacts/chaos-preview');
 await mkdir(output,{recursive:true});
 const browser=await chromium.launch();
 try{
  const page=await browser.newPage({viewport:{width:1100,height:1100},deviceScaleFactor:1});
  await page.goto(pathToFileURL(join(source,'index.html')).href);
  const seek=async frame=>page.locator('#timeline').evaluate((el,n)=>{el.value=String(n);el.dispatchEvent(new Event('input',{bubbles:true}));},frame);
  await page.screenshot({path:join(output,'desktop.png'),fullPage:true});
  await page.locator('.stage').screenshot({path:join(output,'poster.png')});
  const last=Number(await page.locator('#timeline').getAttribute('max')),samples=[];
  for(let sample=0;sample<=last;sample+=10){
   await seek(sample);samples.push(sample);
   await page.locator('.stage').screenshot({path:join(output,`${String(samples.length-1).padStart(4,'0')}.png`)});
  }
  await writeFile(join(output,'samples.json'),JSON.stringify(samples)+'\n');
  await page.setViewportSize({width:390,height:844});
  await page.locator('#peak').click();
  await page.screenshot({path:join(output,'mobile.png'),fullPage:true});
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
