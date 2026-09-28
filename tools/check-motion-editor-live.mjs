import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome,referencePath]=process.argv.slice(2);await fs.mkdir(output);
const reference=JSON.parse(await fs.readFile(referencePath,'utf8'));
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[],results=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.route('**/*',route=>{assert.equal(route.request().method(),'GET');return route.continue();});
  await page.goto('http://127.0.0.1:8918/motion-editor.html');
  await page.waitForFunction(()=>document.querySelectorAll('#source option').length>1&&document.querySelectorAll('#project option').length>1);
  await page.selectOption('#project','alice');await page.selectOption('#source','motion-2671c6fdbc10444592420e6f8f4ad838');
  await page.waitForFunction(()=>window.motionEditorPreviewState?.status==='raw_preview',null,{timeout:60000});
  const seek=async t=>{await page.locator('#time').evaluate((el,t)=>{el.value=String(t);el.dispatchEvent(new Event('input'));},t);
    await page.waitForFunction(t=>Math.abs(window.motionEditorPreviewState?.time-t)<.001,t);};
  const angle=async yaw=>{await page.locator('#yaw-value').fill(String(yaw));await page.locator('#yaw-value').dispatchEvent('change');
    await page.waitForFunction(yaw=>window.motionEditorPreviewState?.keys.length===1&&window.motionEditorPreviewState.keys[0].yaw===yaw,yaw);};
  await angle(30);
  for(const name of ['fixed','turn']){
    if(name==='turn'){
      await seek(0);await angle(0);await page.click('#key');
      await seek(reference.turn.at(-1).time);await angle(360);await page.click('#key');
      await page.waitForFunction(()=>window.motionEditorPreviewState?.keys.length===2);
    }
    for(const row of reference[name]){
      await seek(row.time);const state=await page.evaluate(()=>window.motionEditorPreviewState);
      let error=0;
      for(const bone of state.bones)for(let i=0;i<6;i++){assert.ok(Number.isFinite(bone.matrix[i]));error=Math.max(error,Math.abs(bone.matrix[i]-row.bones[bone.name][i]));}
      assert.ok(error<.001,`${name}/${row.time}: ${error}`);results.push({name,time:row.time,error,state});
      await page.screenshot({path:path.join(output,`${name}-${results.length}.png`)});
    }
    await seek(0);
  }
  await page.selectOption('#project','lumia');await page.selectOption('#project','alice');
  await page.waitForFunction(()=>window.motionEditorPreviewState?.character_artifact==='6e5c59db4ef072075b798efab12acf8ffdc883368a61a4bf3c1646305ef68b98',null,{timeout:60000});
  await page.selectOption('#source','');await page.waitForFunction(()=>window.motionEditorPreviewState===null);
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({passed:true,results,errors,scope:'live_raw_pose_runtime_matches_backend_at_sampled_times'},null,2));
}finally{await browser.close();}
