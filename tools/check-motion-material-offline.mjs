import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(process.argv[2]),event=JSON.parse(await fs.readFile(path.join(root,'event.json'),'utf8'));
const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
 const page=await browser.newPage(),errors=[],network=[];page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>{if(/^https?:/.test(r.url()))network.push(r.url());});
 await page.goto(pathToFileURL(path.join(root,'pose-preview.html')).href);
 await page.waitForFunction(t=>Math.abs((window.characterPlayerState?.time??-1)-t)<.000001||window.characterPlayerError,event.event.time,{timeout:120000});
 assert.equal(await page.evaluate(()=>window.characterPlayerError||null),null);
 assert.equal(await page.evaluate(()=>characterPlayerControl.artifact),event.artifact_sha256);
 await page.waitForFunction(()=>window.characterTriangleInspection);
 const state=await page.evaluate(()=>characterTriangleInspection);
 assert.equal(state.index,event.event.triangle);assert.equal(state.slot,event.slot);
 await page.locator('#time').evaluate(el=>{el.value='0';el.dispatchEvent(new Event('input'));});
 assert.equal(await page.evaluate(()=>characterPlayerState.time),0);
 assert.deepEqual(network,[]);assert.deepEqual(errors,[]);
 console.log(JSON.stringify({passed:true,artifact:event.artifact_sha256,time:event.event.time,slot:event.slot,network_requests:0}));
}finally{await browser.close();}
