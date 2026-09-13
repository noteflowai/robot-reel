const {chromium}=require('playwright');
const {mkdir,readFile,writeFile}=require('node:fs/promises');
const {resolve}=require('node:path');
const {pathToFileURL}=require('node:url');

(async()=>{
  const site=resolve(process.argv[2]),output=resolve(process.argv[3]);
  const trace=JSON.parse(await readFile(resolve(site,'trace.json'),'utf8'));
  const samples=Array.from({length:Math.floor((trace.frame_count-1)/3)+1},(_,i)=>i*3);
  await mkdir(output,{recursive:true});
  const browser=await chromium.launch();
  const page=await browser.newPage({viewport:{width:1024,height:1100},reducedMotion:'reduce'});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  try{
    await page.goto(pathToFileURL(resolve(site,'index.html')).href);
    await page.addStyleTag({content:'.workspace{display:block}.inspector{display:none}#scene{height:480px}.camera{display:none}.axis-note{bottom:16px}'});
    const capture=async(sample,name)=>{
      await page.locator('#timeline').evaluate((el,value)=>{el.value=value;el.dispatchEvent(new Event('input'));},sample);
      if(await page.locator('#counter').textContent()!==`Sample ${sample} / ${trace.frame_count-1}`)throw new Error('Incorrect preview source sample');
      await page.locator('.stage').screenshot({path:resolve(output,name)});
    };
    await capture(trace.summary.peak.frame,'poster.png');
    for(const [i,sample]of samples.entries())await capture(sample,`${String(i).padStart(3,'0')}.png`);
    if(errors.length)throw new Error(errors.join('\n'));
    await writeFile(resolve(output,'samples.json'),JSON.stringify(samples));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
