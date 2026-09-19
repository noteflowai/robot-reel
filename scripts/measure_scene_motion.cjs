// Single-machine replay measurements. No inference, simulator or synthetic delay.
const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const {spawn,execFileSync}=require('node:child_process');
const readline=require('node:readline');
const crypto=require('node:crypto');

async function processTreeRss(root){
 const pending=[root],seen=new Set();let bytes=0;
 while(pending.length){
  const pid=pending.pop();if(seen.has(pid))continue;seen.add(pid);
  try{
   const [status,children]=await Promise.all([
    fs.readFile(`/proc/${pid}/status`,'utf8'),fs.readFile(`/proc/${pid}/task/${pid}/children`,'utf8'),
   ]);
   const match=status.match(/^VmRSS:\s+(\d+)\s+kB/m);if(match)bytes+=Number(match[1])*1024;
   pending.push(...children.trim().split(/\s+/).filter(Boolean).map(Number));
  }catch{}
 }
 return {bytes,processes:seen.size};
}
async function main(){
 const root=path.resolve(process.argv[2]||'docs/scene-lab'),output=path.resolve(process.argv[3]||'artifacts/scene-performance');
 await fs.mkdir(output,{recursive:true});
 const manifest=await fs.readFile(path.join(root,'manifest.json'));
 await fs.writeFile(path.join(output,'measured-site-manifest.json'),manifest);
 const report={
  schema:'robot-reel.scene-performance.v1',started_at:new Date().toISOString(),
  host:{platform:os.platform(),release:os.release(),cpu:os.cpus()[0].model,logical_cpus:os.cpus().length,ram_bytes:os.totalmem()},
  gpu_before:execFileSync('nvidia-smi',['--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu','--format=csv,noheader'],{encoding:'utf8'}).trim(),
  measured_site_manifest:{sha256:crypto.createHash('sha256').update(manifest).digest('hex'),bytes:manifest.length},
  protocol:{case:'baseline',source_replay_hz:30,warmup_seconds:3,measurement_seconds:10,device_scale_factor:1,
   render_camera:'recorded',automatic_adaptation:false,network:'localhost HTTP, browser cache disabled',
   memory:'Sum of RSS in the owned Chromium process subtree; shared pages may count more than once. JS heap is sampled separately. Neither is GPU VRAM.',
   viewport:'390 px is a narrow viewport on this server, not a physical phone.',
   scope:'Browser replay only, with no inference or physics. No injected CPU delay. Desktop display services remain active.'},
  configurations:[],
 };
 const server=spawn('python3',['-u','-m','http.server','0','--bind','127.0.0.1','--directory',root],{stdio:['ignore','pipe','ignore']});
 try{
  const port=await new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>reject(new Error('HTTP server did not start')),10000);
   readline.createInterface({input:server.stdout}).on('line',line=>{const m=line.match(/port (\d+)/);if(m){clearTimeout(timer);resolve(m[1]);}});
  });
  for(const backend of ['vulkan','default'])for(const width of [1440,390]){
   const args=backend==='vulkan'?['--use-angle=vulkan','--enable-features=Vulkan','--disable-vulkan-surface']:[];
   const browserServer=await chromium.launchServer({args});
   let browser;
   try{
    browser=await chromium.connect(browserServer.wsEndpoint());
    const page=await browser.newPage({viewport:{width,height:1100},deviceScaleFactor:1});
    const cdp=await page.context().newCDPSession(page);
    await cdp.send('Network.enable');await cdp.send('Network.setCacheDisabled',{cacheDisabled:true});await cdp.send('Performance.enable');
    let transfer=0;const errors=[];
    cdp.on('Network.loadingFinished',event=>{transfer+=event.encodedDataLength;});
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(`http://127.0.0.1:${port}/`);
    await page.waitForFunction(()=>typeof motion!=='undefined'&&motion!==null&&document.getElementById('poster').complete);
    const initialBytes=transfer;
    await page.locator('.motion-details').evaluate(element=>element.open=true);
    await page.locator('#automatic-detail').uncheck();
    const start=await page.evaluate(()=>performance.now());
    await page.locator('#load').click();
    await page.waitForFunction(()=>document.getElementById('status').textContent.startsWith('Showing'),null,{timeout:120000});
    const ready=await page.evaluate(()=>performance.now());
    const configuration={
     backend_requested:backend,args,browser:browser.version(),viewport:{width,height:1100,device_scale_factor:1},
     initial_http_bytes:initialBytes,http_bytes_through_3d_ready:transfer,click_to_ui_ready_ms:ready-start,
     graphics:await page.evaluate(()=>{
      const gl=app.renderer.getContext(),extension=gl.getExtension('WEBGL_debug_renderer_info');
      return {renderer:extension?gl.getParameter(extension.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER),
       vendor:extension?gl.getParameter(extension.UNMASKED_VENDOR_WEBGL):gl.getParameter(gl.VENDOR),
       stage_css:{width:document.getElementById('stage').clientWidth,height:document.getElementById('stage').clientHeight},
       recorded_viewport:motion.state.viewport};
     }),measurements:[],
    };
    if(backend==='vulkan'&&!configuration.graphics.renderer.includes('NVIDIA'))throw new Error('Requested GPU run did not use NVIDIA');
    for(const quality of ['full','bounds']){
     await page.locator('#motion-quality').selectOption(quality);
     await page.waitForFunction(value=>motion.state.quality===value&&!app.renderer.domElement.hidden,quality);
     await page.locator('#stage').scrollIntoViewIfNeeded();
     await page.evaluate(()=>{
      motion.pause();
      window.sceneMeasurement={start:performance.now(),times:[],raf:0,active:true};
      const drive=now=>{
       const sample=Math.floor((now-window.sceneMeasurement.start)/1000*30)%181;
       if(sample!==motion.state.frame)motion.seek(sample,{share:false});
       if(window.sceneMeasurement.active)window.sceneMeasurement.raf=requestAnimationFrame(drive);
      };
      window.sceneMeasurement.raf=requestAnimationFrame(drive);
      app.renderer.setAnimationLoop(now=>{app.renderLoop(now);window.sceneMeasurement.times.push(now);});
     });
     await page.waitForTimeout(3000);
     await page.evaluate(()=>{window.sceneMeasurement.times=[];window.sceneMeasurement.observedStart=performance.now();});
     let peakRss=0,peakJsHeap=0,peakProcessCount=0,memorySamples=0,busy=false;
     const sample=async()=>{
      if(busy)return;busy=true;
      try{
       const [rss,performance]=await Promise.all([processTreeRss(browserServer.process().pid),cdp.send('Performance.getMetrics')]);
       peakRss=Math.max(peakRss,rss.bytes);peakProcessCount=Math.max(peakProcessCount,rss.processes);
       peakJsHeap=Math.max(peakJsHeap,performance.metrics.find(row=>row.name==='JSHeapUsedSize')?.value||0);
       memorySamples++;
      }finally{busy=false;}
     };
     const timer=setInterval(()=>sample().catch(()=>{}),500);
     try{await sample();await page.waitForTimeout(10000);await sample();}finally{clearInterval(timer);}
     const measured=await page.evaluate(()=>{
      const record=window.sceneMeasurement;record.active=false;cancelAnimationFrame(record.raf);
      app.renderer.setAnimationLoop(app.renderLoop);
      const end=performance.now(),intervals=record.times.slice(1).map((t,i)=>t-record.times[i]).sort((a,b)=>a-b);
      return {observed_ms:end-record.observedStart,rendered_frames:record.times.length,
       render_frames_per_second:record.times.length*1000/(end-record.observedStart),
       median_frame_interval_ms:intervals[Math.floor(intervals.length*.5)],
       p95_frame_interval_ms:intervals[Math.floor(intervals.length*.95)],
       renderer_memory_counts:{...app.renderer.info.memory},draw:{...app.renderer.info.render},
       pixel_ratio:app.renderer.getPixelRatio(),final_source_frame:motion.state.frame};
     });
     if(!peakRss||!peakJsHeap||!measured.rendered_frames)throw new Error('Missing rendering or memory measurements');
     configuration.measurements.push({quality,...measured,peak_sampled_chromium_tree_rss_bytes:peakRss,
      peak_sampled_process_count:peakProcessCount,peak_sampled_js_heap_used_bytes:peakJsHeap,memory_samples:memorySamples});
     console.log(`${backend} ${width}px ${quality}: ${measured.render_frames_per_second.toFixed(1)} render frames/s`);
    }
    if(errors.length)throw new Error(JSON.stringify(errors));
    configuration.errors=errors;report.configurations.push(configuration);
    await fs.writeFile(path.join(output,'performance.json'),JSON.stringify(report,null,2)+'\n');
   }finally{await browser?.close();await browserServer.close();}
  }
  report.finished_at=new Date().toISOString();
  report.gpu_after=execFileSync('nvidia-smi',['--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu','--format=csv,noheader'],{encoding:'utf8'}).trim();
  await fs.writeFile(path.join(output,'performance.json'),JSON.stringify(report,null,2)+'\n');
 }finally{server.kill('SIGTERM');}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
