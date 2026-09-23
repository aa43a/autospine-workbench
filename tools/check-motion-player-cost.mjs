// Local-file delivery benchmark; not production network latency or visual acceptance.
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const [folder,output]=process.argv.slice(2),root=path.resolve(folder);
const raw=await fs.readFile(path.join(root,'player-assets/scene.json'));
const scene=JSON.parse(raw),browser=await chromium.launch({channel:'chrome',headless:true,
 args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
 const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('http://m4-cost.test/**',async route=>{
  const filename=path.resolve(root,'.'+decodeURIComponent(new URL(route.request().url()).pathname));
  assert(filename.startsWith(root+path.sep));
  const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json'};
  await route.fulfill({body:await fs.readFile(filename),contentType:types[path.extname(filename)]||'application/octet-stream'});
 });
 const start=performance.now();await page.goto('http://m4-cost.test/player.html');
 await page.waitForFunction(()=>window.characterPlayerReady||window.characterPlayerError,null,{timeout:120000});
 const readyMs=performance.now()-start;
 const metrics=await page.evaluate(async()=>{
  if(window.characterPlayerError)throw Error(window.characterPlayerError);
  const control=window.characterPlayerControl,canvas=document.querySelector('canvas'),gl=canvas.getContext('webgl');
  const ext=gl.getExtension('WEBGL_debug_renderer_info');
  const duration=window.characterPlayerState.duration,samples=[];
  for(let i=0;i<65;i++){
   await new Promise(requestAnimationFrame);
   const time=duration*((i*37)%61)/60,start=performance.now();
   if(!control.seek(time))throw Error('seek failed');gl.finish();
   if(i>=5)samples.push(performance.now()-start);
  }
  control.seek(0);gl.finish();
  return {artifact:control.artifact,duration,canvas:[canvas.width,canvas.height],
   renderer:ext?gl.getParameter(ext.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER),samples};
 });
 assert.equal(metrics.artifact,scene.artifact_sha256);assert.deepEqual(errors,[]);
 const sorted=[...metrics.samples].sort((a,b)=>a-b);
 const report={scope:'60 synchronous reverse/forward seeks including gl.finish; five warmups; headless SwiftShader; no hardware GPU or network SLA claim',
  browser:browser.version(),platform:os.platform(),cpu:os.cpus()[0].model,logical_cpus:os.cpus().length,
  scene_bytes:raw.length,slots:scene.skeleton.slots.length,ready_ms:readyMs,...metrics,
  median_ms:sorted[Math.floor(sorted.length*.5)],p95_ms:sorted[Math.ceil(sorted.length*.95)-1],max_ms:sorted.at(-1),visual_accepted:false};
 await fs.writeFile(output,JSON.stringify(report,null,2));console.log(JSON.stringify({...report,samples:undefined}));
}finally{await browser.close();}
