// Actual local Kimodo submission or recovery; never resubmit on an observation timeout.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome,resume]=process.argv.slice(2);
await fs.mkdir(output,{recursive:true});
const saved=path.join(output,'submitted.json');
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  let job;
  if(resume){
    job=JSON.parse(await fs.readFile(saved,'utf8'));
    await page.addInitScript(id=>localStorage.setItem('autospine-motion-editor-source-job-v1',id),job.job_id);
  }else{
    await assert.rejects(fs.access(saved),'Existing submission must be resumed');
  }
  await page.goto('http://127.0.0.1:8918/motion-editor.html');
  await page.waitForFunction(()=>document.querySelectorAll('#source option').length>1);
  await page.locator('.intake summary').click();
  if(!resume){
    await page.fill('#intake-prompt','A person stands still and breathes gently.');
    await page.fill('#intake-duration','1');await page.fill('#intake-steps','10');await page.fill('#intake-seed','20260929');
    const response=page.waitForResponse(r=>r.url().endsWith('/api/motions/generate')&&r.request().method()==='POST');
    await page.click('#intake-generate');const submitted=await response;
    assert.equal(submitted.status(),202);job=await submitted.json();
    await fs.writeFile(saved,JSON.stringify(job,null,2));
    await fs.writeFile(path.join(output,'request.json'),JSON.stringify(submitted.request().postDataJSON(),null,2));
  }
  const current=await (await page.request.get(`http://127.0.0.1:8918/api/motions/${job.job_id}`)).json();
  if(current.status==='succeeded'){
    await page.waitForFunction(()=>!document.querySelector('#intake-load').disabled);
    assert.equal(await page.locator('#source').inputValue(),'');
    await page.click('#intake-load');
    await page.waitForFunction(id=>document.querySelector('#source').value===id,job.job_id);
    await page.selectOption('#project','alice');
    await page.waitForFunction(()=>window.motionEditorPreviewState?.status==='raw_preview',{},{timeout:60000});
    await page.fill('#yaw-value','30');await page.locator('#yaw-value').dispatchEvent('change');
    await page.click('#undo-edit');assert.equal(Number(await page.locator('#yaw-value').inputValue()),0);
    await page.click('#redo-edit');assert.equal(Number(await page.locator('#yaw-value').inputValue()),30);
    await page.click('#undo-edit');
    await page.locator('#time').evaluate(el=>{el.value=el.max;el.dispatchEvent(new Event('input'));});
    await page.fill('#yaw-value','45');await page.locator('#yaw-value').dispatchEvent('change');await page.click('#key');
    await page.waitForFunction(()=>window.motionEditorPreviewState?.keys.length===2);
    await page.click('#undo-edit');await page.waitForFunction(()=>window.motionEditorPreviewState?.keys.length===1);
    await page.click('#redo-edit');await page.waitForFunction(()=>window.motionEditorPreviewState?.keys.length===2);
  }else if(['pending','queued','running','cancelling'].includes(current.status)){
    await page.waitForFunction(()=>document.querySelector('#intake-generate').disabled);
  }
  assert.deepEqual(errors,[]);
  await page.screenshot({path:path.join(output,`${resume?'recovered':'submitted'}.png`),fullPage:true});
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({job:current,loaded:current.status==='succeeded',errors},null,2));
  console.log(JSON.stringify({id:job.job_id,status:current.status,step:current.step}));
}finally{await browser.close();}
