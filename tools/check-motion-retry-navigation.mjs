// Browser UI contract only: retry/list responses are isolated; no real job is launched.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [base,jobId,output,dependencies]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try {
  const page=await browser.newPage();let submitted=false;
  const next='motion-'+'e'.repeat(32),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const inventory=await (await page.request.get(new URL('/api/motions',base).href)).json();
  const original=inventory.jobs.find(j=>j.job_id===jobId);assert.equal(original.kind,'adapt');
  await page.route('**/api/motions',async route=>{
    assert.equal(route.request().method(),'GET');
    await route.fulfill({json:{...inventory,jobs:submitted
      ?[{...original,job_id:next,status:'pending',step:'queued'},original]:[original]}});
  });
  await page.route(`**/api/motions/${jobId}/retry`,async route=>{
    assert.equal(route.request().method(),'POST');
    assert.equal(route.request().headers()['x-autospine-intent'],'pipeline-preview');
    submitted=true;await route.fulfill({status:202,json:{job_id:next,status:'pending'}});
  });
  await page.goto(new URL('/motions.html#'+jobId,base).href);
  await page.locator('#'+jobId).getByRole('button',{name:'重新构建角色动作（保留旧记录）',exact:true}).click();
  await page.waitForFunction(id=>location.hash==='#'+id,next);
  await page.locator('#'+next).getByRole('button',{name:'取消任务',exact:true}).waitFor();
  assert.equal(await page.locator('#'+jobId).count(),1);
  assert.deepEqual(errors,[]);
  await fs.mkdir(output,{recursive:true});
  await fs.writeFile(path.join(output,'navigation.json'),JSON.stringify({passed:true,
    scope:'browser_contract_with_intercepted_retry_and_list_no_actual_job',original:jobId,newJob:next,errors},null,2));
  console.log('Retry navigation and preserved original card passed (intercepted job responses)');
} finally {await browser.close();}
