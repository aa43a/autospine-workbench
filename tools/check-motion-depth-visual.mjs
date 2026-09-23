// Read-only screenshots of the unchanged official Runtime player at exact times.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const [base,job,output]=process.argv.slice(2);
const browser=await chromium.launch({channel:'chrome',headless:true,
  args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
 const page=await browser.newPage({viewport:{width:1100,height:1400}});const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const response=await page.request.get(`${base}/api/motions/${job}`);assert.equal(response.status(),200);
 const task=await response.json();assert.equal(task.status,'succeeded');
 await page.goto(`${base}/api/motions/${job}/view/player.html`);
 await page.waitForFunction(()=>window.characterPlayerReady||window.characterPlayerError,null,{timeout:120000});
 assert.equal(await page.evaluate(()=>window.characterPlayerError),undefined);
 assert.equal(await page.evaluate(()=>window.characterPlayerControl.artifact),task.result.artifact_sha256);
 await page.addStyleTag({content:'canvas{width:auto!important;height:auto!important;max-height:none!important} .viewport{height:auto!important;max-height:none!important}'});
 await fs.mkdir(output,{recursive:true});const rows=[];
 for(const time of [1,1.5,2])for(const [mode,regions] of [['full',[]],['isolate',['layer-003','layer-006']],['isolate',['layer-003']]]){
   const state=await page.evaluate(({time,mode,regions})=>{
     const control=window.characterPlayerControl;
     if(!control.inspectRegions(regions,mode)||!control.seek(time))throw Error('inspection_failed');
     return {time:window.characterPlayerState.time,...window.characterInspectionState};
   },{time,mode,regions});
   assert.equal(state.time,time);
   const file=`frame-${time}-${regions.length}.png`;
   await page.locator('canvas').screenshot({path:path.join(output,file)});
   rows.push({file,...state});
 }
 assert.deepEqual(errors,[]);
 await fs.writeFile(path.join(output,'report.json'),JSON.stringify({job,artifact:task.result.artifact_sha256,rows,
   scope:'unchanged_player_screenshots_not_depth_truth_or_visual_acceptance'},null,2));
 console.log(JSON.stringify({job,frames:rows.length,passed:true}));
}finally{await browser.close();}
