// Render the measured browser poses into PNGs for a shareable preview.
// node scripts/render_newton_preview.cjs [bundle] [output]
const {chromium}=require('playwright');
const {mkdir}=require('node:fs/promises');
const {resolve,join}=require('node:path');
const {pathToFileURL}=require('node:url');
(async()=>{
 const source=resolve(process.argv[2]||'docs/newton');
 const output=resolve(process.argv[3]||'artifacts/newton-preview');
 await mkdir(output,{recursive:true});
 const browser=await chromium.launch();
 try{
  const page=await browser.newPage({viewport:{width:1200,height:1050},deviceScaleFactor:1});
  await page.goto(pathToFileURL(join(source,'index.html')).href);
  const seek=async frame=>page.locator('#timeline').evaluate((el,frame)=>{el.value=String(frame);el.dispatchEvent(new Event('input',{bubbles:true}));},frame);
  await seek(30);
  await page.screenshot({path:join(output,'preview.png')});
  const last=Number(await page.locator('#timeline').getAttribute('max'));
  for(let sample=0,i=0;sample<=last;sample+=3,i++){
   await seek(sample);
   await page.locator('.workspace').screenshot({path:join(output,`${String(i).padStart(4,'0')}.png`)});
  }
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:join(output,'mobile.png'),fullPage:true});
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
