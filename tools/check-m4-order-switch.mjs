// Capture identical-time before/after canvases around a discrete order transition.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [url,deps,chrome,output,boundaryText]=process.argv.slice(2);
const boundary=Number(boundaryText);
assert.ok(Number.isFinite(boundary)&&boundary>0);
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
  const page=await browser.newPage({viewport:{width:1600,height:1200}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(url);
  await page.waitForFunction(()=>window.reachComparisonState?.ready||window.reachComparisonError,null,{timeout:120000});
  assert.equal(await page.evaluate(()=>window.reachComparisonError),undefined);
  await fs.mkdir(output,{recursive:true});
  const records=[];
  for(const [label,time] of [['prior',boundary-.000001],['switch',boundary],['following',boundary+.000001],['raised',2.4]]) {
    // Use the player's exact seek API: an HTML range control can quantize microseconds.
    const states=await page.evaluate(time=>['left','right'].map(id=>{
      const w=document.getElementById(id).contentWindow;
      assertSeek(w.characterPlayerControl.seek(time));return w.characterPlayerState;
      function assertSeek(ok){if(!ok)throw Error('seek rejected');}
    }),time);
    for(const [i,id] of ['left','right'].entries()) {
      assert.ok(Math.abs(states[i].time-time)<1e-8);
      await page.frameLocator('#'+id).locator('canvas').screenshot({path:path.join(output,`${label}-${id}.png`)});
    }
    records.push({label,time});
  }
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'capture.json'),JSON.stringify({authority:'none',records,errors},null,2));
} finally {await browser.close();}
