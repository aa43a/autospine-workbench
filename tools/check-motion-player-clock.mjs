import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const [base,job]=process.argv.slice(2);
const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
 const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{
  let clock=1000,queue=[];
  performance.now=()=>clock;
  window.requestAnimationFrame=callback=>{queue.push(callback);return queue.length;};
  window.advanceTestClock=milliseconds=>{clock+=milliseconds;const batch=queue;queue=[];for(const callback of batch)callback(clock);};
 });
 await page.goto(`${base}/api/motions/${job}/view/player.html`);
 await page.waitForFunction(()=>window.characterPlayerReady,null,{timeout:120000,polling:100});
 const advance=ms=>page.evaluate(ms=>advanceTestClock(ms),ms);
 const toggle=()=>page.locator('#play').evaluate(el=>el.click());
 const state=()=>page.evaluate(()=>characterPlayerState);
 await toggle();await advance(250);
 assert.equal((await state()).time,.25);
 await page.locator('#speed').selectOption('2');await advance(250);
 assert.equal((await state()).time,.75);
 await toggle();await advance(1000);assert.equal((await state()).time,.75);
 await toggle();await advance(250);assert.equal((await state()).time,1.25);
 const duration=(await state()).duration;
 await advance(duration*3000);
 assert.ok(Math.abs((await state()).time-1.25)<.000001); // Three periods at speed 2 -> six loops.
 await page.locator('#loop').evaluate(el=>el.checked=false);
 await page.evaluate(()=>characterPlayerControl.seek(characterPlayerState.duration-.05));
 await toggle();await advance(250);
 assert.equal((await state()).time,duration);assert.equal((await state()).playing,false);
 await toggle();await advance(250);assert.equal((await state()).time,.5);
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({passed:true,job,duration,scope:'actual Runtime with deterministic delayed frame callbacks; no animation data changes',
  checks:['250ms_stall','speed','pause_resume','multiple_loops','end_clamp','restart']}));
}finally{await browser.close();}
