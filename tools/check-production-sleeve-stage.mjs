import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome]=process.argv.slice(2);
await fs.mkdir(output,{recursive:true});
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true});
try {
  const page=await browser.newPage(), errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  const run={run_id:'production-'+'a'.repeat(32),revision:1,status:'blocked',
    reason_code:'sleeve_annotation_required',request:{project_id:'huiye'},
    stages:{source:{status:'succeeded'},bindings:{status:'succeeded'},
      sleeves:{status:'blocked'},character:{status:'pending'},delivery:{}}};
  // Only the list is a fixture. No mutation, source edit, build or acceptance.
  await page.route('**/api/production',async route=>{
    assert.equal(route.request().method(),'GET');
    await route.fulfill({json:{runs:[run]}});
  });
  await page.goto('http://127.0.0.1:8918/production.html?run='+run.run_id);
  await page.getByRole('link',{name:'打开袖装标注',exact:true}).waitFor();
  assert.equal(await page.getByRole('link',{name:'打开袖装标注',exact:true}).getAttribute('href'),
    '/api/projects/huiye/automation/sleeves/annotation/view');
  assert.match(await page.locator('#stages').innerText(),/袖装候选与 Runtime/);
  assert.match(await page.locator('#detail').innerText(),/保存当前袖装区域标注/);
  await page.getByRole('button',{name:'重试失败步骤',exact:true}).waitFor();
  run.status='running'; delete run.reason_code; run.stages.sleeves.status='running';
  await page.reload();
  await page.waitForFunction(()=>document.querySelector('#stages')?.innerText.includes('袖装候选与 Runtime'));
  assert.match(await page.locator('#stages').innerText(),/处理中/);
  assert.equal(await page.getByRole('button',{name:'重试失败步骤',exact:true}).count(),0);
  assert.deepEqual(errors,[]);
  await page.screenshot({path:path.join(output,'sleeve-stage.png'),fullPage:true});
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({passed:true,
    scope:'UI fixture only; no real build or human acceptance',errors},null,2));
  console.log(JSON.stringify({passed:true,scope:'UI fixture'}));
} finally {await browser.close();}
