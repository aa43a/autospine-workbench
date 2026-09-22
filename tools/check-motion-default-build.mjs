// Real UI submission. Writes the returned job immediately; never retries a timed-out build.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [base,sourceId,projectId,output,dependencies]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try {
  await fs.mkdir(output,{recursive:true});
  await fs.writeFile(path.join(output,'attempt.json'),JSON.stringify({sourceId,projectId,
    startedAt:new Date().toISOString(),note:'Single attempt. Inspect server jobs before any resubmission.'}),{flag:'wx'});
  const page=await browser.newPage({viewport:{width:1400,height:1000}});
  await page.goto(new URL('/motions.html#'+sourceId,base).href);
  await page.locator('#'+sourceId).getByRole('button',{name:'查看源动作',exact:true}).click();
  await page.locator('#target-project').selectOption(projectId);
  await page.waitForFunction(()=>!document.getElementById('adapt').disabled,{},{timeout:120000});
  const responsePromise=page.waitForResponse(r=>r.url().endsWith(`/api/motions/${sourceId}/adapt`)&&r.request().method()==='POST',{timeout:120000});
  await page.locator('#adapt').click();
  const response=await responsePromise,receipt=await response.json();
  assert.equal(response.status(),202,JSON.stringify(receipt));
  await fs.writeFile(path.join(output,'submitted.json'),JSON.stringify({sourceId,projectId,
    request:response.request().postDataJSON(),receipt,submittedAt:new Date().toISOString()},null,2),{flag:'wx'});
  assert.equal(response.request().postDataJSON().contact_correction,true);
  assert.equal(response.request().postDataJSON().clip,null);
  assert.equal(response.request().postDataJSON().pose_profile,undefined);
  await page.waitForFunction(id=>location.hash==='#'+id,receipt.job_id);
  await page.locator('#'+receipt.job_id).waitFor();
  await page.screenshot({path:path.join(output,'queued.png')});
  console.log(JSON.stringify({submitted:true,jobId:receipt.job_id,sourceId,projectId}));
} finally {await browser.close();}
