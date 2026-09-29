import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome,psd]=process.argv.slice(2);
await fs.mkdir(output,{recursive:true});
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true});
try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto('http://127.0.0.1:8918/production.html');
  await page.waitForFunction(()=>document.querySelectorAll('#source option').length>1);
  await page.locator('details > summary').first().click();
  await page.setInputFiles('#psd-file',psd);
  await page.click('#psd-submit');
  await page.waitForFunction(()=>document.getElementById('project').value.startsWith('imported-'),null,{timeout:120000});
  const project=await page.inputValue('#project');
  await page.selectOption('#source','motion-2671c6fdbc10444592420e6f8f4ad838');
  const response=page.waitForResponse(r=>r.url().endsWith('/api/production')&&r.request().method()==='POST');
  await page.click('#start');const submitted=await response;
  assert.equal(submitted.status(),202,await submitted.text());
  assert.equal(submitted.request().postDataJSON().character_job_id,null);
  const run=await submitted.json();
  await page.screenshot({path:path.join(output,'intake.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({passed:true,project,run_id:run.run_id,scope:'new_psd_import_and_preparation_dispatch_not_full_acceptance',errors},null,2));
  console.log(JSON.stringify({project,run_id:run.run_id}));
}finally{await browser.close();}
