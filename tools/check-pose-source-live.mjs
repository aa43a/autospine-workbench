import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const [url, output, dependency] = process.argv.slice(2);
const {chromium} = await import(pathToFileURL(dependency));
const browser = await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try {
  const page = await browser.newPage({viewport:{width:1300,height:1100}}), errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(url);
  await page.waitForFunction(()=>window.poseGeometryEditorReady||window.poseGeometryEditorError,{},{timeout:60000});
  assert.equal(await page.evaluate(()=>window.poseGeometryEditorError),undefined);
  await page.waitForFunction(()=>!document.getElementById('source-reference').hidden||document.getElementById('source-error').textContent,{},{timeout:60000});
  assert.equal(await page.locator('#source-error').textContent(),'');
  const source = await (await page.request.get(new URL('source-comparison.json',url).href)).json();
  assert.equal(source.artifact_sha256,await page.evaluate(()=>window.poseGeometryEditorState.artifact));
  const checks=[];
  for (const time of [.1,.7,1.2]) {
    await page.locator('#time').evaluate((el,time)=>{el.value=time;el.dispatchEvent(new Event('input'));},time);
    const value = Number(await page.locator('#source-position').getAttribute('data-requested-time'));
    assert.ok(Math.abs(value-source.source_start-time)<1e-6);
    checks.push({time,source_time:value,sample:await page.locator('#source-position').textContent()});
  }
  await page.locator('#source-view').selectOption('side');
  assert.equal(await page.evaluate(()=>window.poseGeometryEditorState.time),1.2);
  await page.locator('#play').click();
  await page.waitForFunction(()=>window.poseGeometryEditorState.time>1.4);
  await page.locator('#play').click();
  const time=await page.evaluate(()=>window.poseGeometryEditorState.time);
  assert.ok(Math.abs(Number(await page.locator('#source-position').getAttribute('data-requested-time'))-source.source_start-time)<1e-6);
  assert.deepEqual(errors,[]);
  await fs.mkdir(output,{recursive:true});
  await page.screenshot({path:output+'/editor.png',fullPage:true});
  await fs.writeFile(output+'/report.json',JSON.stringify({passed:true,url,artifact:source.artifact_sha256,
    source_job:source.source_job_id,source_start:source.source_start,checks,errors,
    scope:'live_read_only_editor_source_sync_not_motion_quality_acceptance'},null,2));
  console.log(JSON.stringify({passed:true,source_job:source.source_job_id,checks}));
} finally {await browser.close();}
