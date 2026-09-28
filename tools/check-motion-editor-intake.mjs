// Real source import; generation transport is stubbed to avoid redundant GPU work.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome,source]=process.argv.slice(2);await fs.mkdir(output);
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto('http://127.0.0.1:8918/motion-editor.html');
  await page.waitForFunction(()=>document.querySelectorAll('#source option').length>1);
  await page.locator('.intake summary').click();
  await page.setInputFiles('#intake-file',source);
  const submitted=page.waitForResponse(r=>r.url().endsWith('/api/motions')&&r.request().method()==='POST');
  await page.click('#intake-import');assert.equal((await submitted).status(),202);
  await page.waitForFunction(()=>localStorage.getItem('autospine-motion-editor-source-job-v1'));
  const id=await page.evaluate(()=>localStorage.getItem('autospine-motion-editor-source-job-v1'));
  const job=await (await page.request.get(`http://127.0.0.1:8918/api/motions/${id}`)).json();
  await fs.writeFile(path.join(output,'import-job.json'),JSON.stringify(job,null,2));
  await page.waitForFunction(()=>!document.querySelector('#intake-load').disabled,{},{timeout:120000});
  assert.equal(await page.locator('#source').inputValue(),''); // completion cannot erase current editing
  await page.reload();await page.waitForFunction(()=>!document.querySelector('#intake-load').disabled);
  await page.click('#intake-load');await page.waitForFunction(id=>document.querySelector('#source').value===id,job.job_id);
  await page.waitForFunction(()=>!document.querySelector('#key').disabled);
  const mock='motion-'+'a'.repeat(32),successor='motion-'+'b'.repeat(32);let generation,mockStatus='pending',retries=0;
  await page.route('**/api/motions/generate',async route=>{
    generation=route.request().postDataJSON();await route.fulfill({status:202,json:{job_id:mock,status:'pending',step:'queued'}});
  });
  await page.route(`**/api/motions/${mock}`,route=>route.fulfill({json:{job_id:mock,kind:'generate',name:'test generation',status:mockStatus,step:mockStatus}}));
  await page.route(`**/api/motions/${mock}/retry`,route=>{retries++;return route.fulfill({status:202,json:{job_id:successor,kind:'generate',status:'pending'}});});
  await page.route(`**/api/motions/${successor}`,route=>route.fulfill({json:{job_id:successor,kind:'generate',name:'retried generation',status:'pending',step:'queued'}}));
  await page.route(`**/api/motions/${mock}/cancel`,route=>route.fulfill({json:{job_id:mock,status:'cancelled'}}));
  await page.locator('.intake summary').click();await page.fill('#intake-prompt','A person slowly raises their right arm.');
  await page.click('#intake-generate');await page.waitForFunction(()=>document.querySelector('#intake-status').textContent.includes('test generation'));
  assert.equal(generation.duration_seconds,4);assert.equal(generation.diffusion_steps,100);
  assert.equal(await page.locator('#intake-generate').isDisabled(),true);
  assert.equal(await page.locator('#source').inputValue(),job.job_id);
  assert.equal(await page.locator('#intake-retry').isDisabled(),true);
  mockStatus='failed';await page.click('#intake-refresh');
  await page.waitForFunction(()=>!document.querySelector('#intake-retry').disabled);
  await page.click('#intake-retry');
  await page.waitForFunction(id=>localStorage.getItem('autospine-motion-editor-source-job-v1')===id,successor);
  assert.equal(retries,1);assert.equal(await page.locator('#source').inputValue(),job.job_id);
  await page.screenshot({path:path.join(output,'editor.png'),fullPage:true});
  assert.deepEqual(errors,[]);await fs.writeFile(path.join(output,'report.json'),JSON.stringify({passed:true,real_import:job.job_id,generation_transport_only:generation,errors},null,2));
}finally{await browser.close();}
