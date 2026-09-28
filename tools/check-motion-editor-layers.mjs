// Exercise actual layer editing, persistence, undo, isolation and adapt submission.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome]=process.argv.slice(2);await fs.mkdir(output,{recursive:true});
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const source='motion-c8f9555203bc4130abeaf37e523a16cb';
try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto('http://127.0.0.1:8918/motion-editor.html');
  await page.waitForFunction(()=>document.querySelectorAll('#source option').length>1&&document.querySelectorAll('#project option').length>1);
  await page.selectOption('#project','yaomeng');await page.selectOption('#source',source);
  await page.waitForFunction(()=>window.motionEditorPreviewState?.status==='raw_preview',null,{timeout:60000});
  await page.selectOption('#motion-layer-list','layer-002');
  assert.match(await page.locator('#layer-selection').innerText(),/handwear-l/);
  await page.locator('.canvases').screenshot({path:path.join(output,'before.png')});
  for(const [key,value] of Object.entries({dx:6,dy:3,rotation:2,scaleX:1.02,scaleY:.98})){
    await page.fill('#layer-'+key,String(value));await page.locator('#layer-'+key).dispatchEvent('change');
  }
  await page.waitForFunction(()=>window.motionEditorPreviewState?.layer_edits?.transforms[0]?.scaleY===.98);
  await page.click('#undo-edit');assert.equal(await page.locator('#layer-scaleY').inputValue(),'1');
  await page.click('#redo-edit');assert.equal(await page.locator('#layer-scaleY').inputValue(),'0.98');
  await page.click('#layer-front');
  assert.equal(await page.locator('#motion-layer-list option').first().getAttribute('value'),'layer-002');
  await page.selectOption('#motion-layer-list','layer-000');
  await page.fill('#layer-dx','4');await page.locator('#layer-dx').dispatchEvent('change');
  await page.click('#save-draft');
  const draft=await page.evaluate(()=>JSON.parse(localStorage.getItem('autospine.motion-editor.draft.v1')));
  assert.equal(draft.layer_edits.transforms.length,2);assert.equal(draft.layer_edits.draw_order.at(-1),'layer-002');
  await page.click('#layer-reset-all');
  await page.click('#restore-draft');
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('草稿已恢复'));
  await page.waitForFunction(()=>window.motionEditorPreviewState?.layer_edits?.transforms.length===2);
  await page.click('#play');await page.waitForFunction(()=>window.motionEditorPreviewState?.time>.15);
  await page.click('#play');
  for(const time of [.72,.12]){
    await page.locator('#time').evaluate((el,t)=>{el.value=t;el.dispatchEvent(new Event('input'));},time);
    await page.waitForFunction(t=>Math.abs(window.motionEditorPreviewState?.time-t)<.001,time);
    assert.equal((await page.evaluate(()=>window.motionEditorPreviewState.layer_edits.transforms)).length,2);
  }
  await page.locator('.canvases').screenshot({path:path.join(output,'edited.png')});
  // Reload browser and recover the same exact character/source-bound draft.
  await page.reload();await page.waitForFunction(()=>document.querySelectorAll('#project option').length>1&&document.querySelectorAll('#source option').length>1);
  await page.selectOption('#project','yaomeng');await page.selectOption('#source',source);
  await page.waitForFunction(()=>window.motionEditorPreviewState?.status==='raw_preview',null,{timeout:60000});
  await page.click('#restore-draft');await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('草稿已恢复'));
  await page.waitForFunction(()=>window.motionEditorPreviewState?.layer_edits?.transforms.length===2);
  const responsePromise=page.waitForResponse(r=>r.url().endsWith('/adapt')&&r.request().method()==='POST');
  await page.click('#build');const response=await responsePromise,value=await response.json();
  assert.equal(response.status(),202,JSON.stringify(value));assert.match(value.job_id,/^motion-/);
  const sent=response.request().postDataJSON();assert.deepEqual(sent.layer_edits,draft.layer_edits);
  await fs.writeFile(path.join(output,'submission.json'),JSON.stringify({job_id:value.job_id,draft,request:sent},null,2));
  await page.selectOption('#project','alice');await page.waitForFunction(()=>document.querySelector('#motion-layer-list').options.length>0&&document.querySelector('#layer-status').textContent.includes('尚无'));
  await page.click('#save-draft');const clean=await page.evaluate(()=>JSON.parse(localStorage.getItem('autospine.motion-editor.draft.v1')));
  assert.equal(clean.project_id,'alice');assert.equal(clean.layer_edits,undefined);
  await page.setViewportSize({width:390,height:844});
  await page.locator('.layer-editor').screenshot({path:path.join(output,'mobile.png')});
  const overflow=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,
    elements:[...document.querySelectorAll('body *')].filter(el=>el.getBoundingClientRect().right>innerWidth+1).map(el=>({tag:el.tagName,id:el.id,right:el.getBoundingClientRect().right}))}));
  await fs.writeFile(path.join(output,'layout.json'),JSON.stringify(overflow,null,2));
  assert.ok(overflow.scroll<=overflow.width,JSON.stringify(overflow));
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({passed:true,job_id:value.job_id,errors,checks:['transform','order','undo_redo','save_restore','reload','play_scrub_reverse','source_bound_submission','project_isolation','mobile']},null,2));
}finally{await browser.close();}
