// Exercise the real production form; creates one independent candidate chain.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome]=process.argv.slice(2);
await fs.mkdir(output,{recursive:true});
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true});
try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto('http://127.0.0.1:8918/production.html');
  await page.waitForFunction(()=>document.querySelectorAll('#source option').length>1);
  await page.selectOption('#project','alice');
  await page.selectOption('#source','motion-2671c6fdbc10444592420e6f8f4ad838');
  const response=page.waitForResponse(r=>r.url().endsWith('/api/production')&&r.request().method()==='POST');
  await page.click('#start');
  const submitted=await response;
  assert.equal(submitted.status(),202,await submitted.text());
  const run=await submitted.json();
  assert.equal(submitted.request().postDataJSON().joint_config.face.enabled,true);
  await page.waitForFunction(id=>location.search.includes(id),run.run_id);
  await page.reload();
  await page.waitForFunction(()=>document.querySelectorAll('#stages li').length>=5);
  await page.screenshot({path:path.join(output,'desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.screenshot({path:path.join(output,'mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({passed:true,run_id:run.run_id,scope:'actual_submit_refresh_mobile_no_visual_acceptance',errors},null,2));
  console.log(JSON.stringify({passed:true,run_id:run.run_id}));
}finally{await browser.close();}
