// Real evidence replayed into the production component; no review/adoption writes.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [evidence,dependencies,chrome]=process.argv.slice(2);
const report=JSON.parse(await fs.readFile(evidence,'utf8'));
const {chromium}=await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true});
try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  let payload=report;
  await page.route('http://knee.test/**',async route=>{
    const pathname=new URL(route.request().url()).pathname;
    if(pathname==='/bend-status.json')return route.fulfill({json:payload});
    if(['/motion-knee-details.js','/motion-knee-model.js'].includes(pathname))return route.fulfill({contentType:'text/javascript',body:await fs.readFile('web/modules'+pathname,'utf8')});
    return route.fulfill({contentType:'text/html',body:`<main></main><script type="module">import {appendKneeDetails} from '/motion-knee-details.js';appendKneeDetails(document.querySelector('main'),'/',${JSON.stringify(report.artifact_sha256)},t=>window.selectedTime=t);</script>`});
  });
  await page.goto('http://knee.test/');
  const button=page.getByRole('button',{name:'检查膝盖方向与深度',exact:true});await button.click();
  const panel=page.getByRole('region',{name:'膝部动作与素材需求'}),slider=panel.getByRole('slider');
  for(const side of ['left','right']){
    await panel.getByRole('combobox').selectOption(side);
    const rows=report.rows.filter(r=>r.side===side);
    for(const index of [rows.length-1,0]){
      await slider.fill(String(index));await slider.dispatchEvent('input');
      await panel.getByRole('button',{name:'在当前时间轴定位',exact:true}).click();
      assert.equal(await page.evaluate(()=>window.selectedTime),rows[index].time);
    }
  }
  await panel.getByRole('button',{name:'下一处需要检查的采样',exact:true}).click();
  assert.ok((await panel.textContent()).includes('不会自动认定缺素材'));
  payload={...report,artifact_sha256:'stale'};await button.click();
  await panel.getByText('无法检查：候选身份变化',{exact:true}).waitFor();assert.equal(await slider.count(),0);
  payload={...report,rows:report.rows.filter(r=>r.side==='left')};await button.click();
  await panel.getByText('无法检查：膝部左右采样缺失',{exact:true}).waitFor();assert.equal(await slider.count(),0);
  payload=structuredClone(report);for(const r of payload.rows)delete r.source.screen_plane_alignment;
  await button.click();await slider.waitFor();assert.ok((await panel.textContent()).includes('未测量'));
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,artifact:report.artifact_sha256,rows:report.rows.length,
    scope:'production_component_real_evidence_replay_not_live_workbench_or_motion_visual_acceptance'}));
}finally{await browser.close();}
