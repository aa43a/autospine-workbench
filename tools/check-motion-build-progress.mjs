// Browser rendering verification with a simulated job lifecycle; no real build is submitted.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome]=process.argv.slice(2);await fs.mkdir(output,{recursive:true});
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true});
try{
  const page=await browser.newPage({viewport:{width:1280,height:900}}),id='motion-'+'a'.repeat(32);let calls=0;
  await page.route(`**/api/motions/${id}`,async route=>{
    calls++;if(calls===2)return route.abort('connectionfailed');
    await route.fulfill({json:{job_id:id,kind:'adapt',name:'模拟进度验证',project_id:'yaomeng',status:calls>=4?'failed':'running',step:'retarget',elapsed_seconds:126+calls*3,timeout_seconds:3600,
      progress:{step:'retarget',stage:'solve_attachment',slot:'layer-002',slot_index:2,total_slots:27,iteration:1,max_rounds:4,updated_at:Date.now()/1000},
      ...(calls>=4?{reason_code:'motion_target_stalled'}:{})}});
  });
  await page.goto(`http://127.0.0.1:8918/motion-editor.html#${id}`);
  await page.waitForFunction(()=>document.querySelector('#build-status').textContent.includes('图层 3 / 27'));
  assert.equal(await page.locator('#build').isDisabled(),true);
  await page.locator('#build-status').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,'running.png')});
  await page.waitForFunction(()=>document.querySelector('#build-status').textContent.includes('自动重试'));
  assert.equal(await page.locator('#build').isDisabled(),true);
  await page.screenshot({path:path.join(output,'retry.png')});
  await page.waitForFunction(()=>document.querySelector('#build-status').textContent.includes('长时间没有更新进度'),null,{timeout:15000});
  assert.equal(await page.locator('#build').isDisabled(),false);
  await page.screenshot({path:path.join(output,'stalled.png')});
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({passed:true,evidence:'simulated job lifecycle in real browser; no build submitted',calls,checks:['observed stage counts','elapsed time','network retry retains lock','terminal state unlocks']},null,2));
}finally{await browser.close();}
