// Read-only actual source/candidate diagnostic UI check.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE);
const state=JSON.parse(await fs.readFile('../tmp/m4-motion-center/cohort-state-v3.json','utf8'));
const source=state.sources.squat,target=state.cells['squat/hongmeiling'];
const pack={version:1,plan_sha256:state.plan_sha256,groups:[{label:'squat',job_id:source.job_id,source_sha256:source.source_sha256,
  targets:[{label:'hongmeiling',job_id:target.job_id,artifact_sha256:target.result.artifact_sha256}]}]};
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,
  args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.goto('http://127.0.0.1:8918/motion-cohort.html#'+encodeURIComponent(JSON.stringify(pack)));
  await page.locator('#review').getByRole('button',{name:'检查膝盖方向与深度'}).click();
  await page.locator('#review').getByRole('button',{name:/可见弯曲方向反转 · 首次/}).first().click({timeout:120000});
  const select=page.getByLabel('局部修正实验',{exact:true});await select.waitFor();
  await select.selectOption(await select.locator('option').nth(1).getAttribute('value'));
  await page.locator('#experiments').getByRole('button',{name:'检查膝盖方向与深度'}).click();
  await page.locator('#experiments').getByRole('button',{name:/目标弯曲投影接近拉直 · 首次/}).first().waitFor({timeout:120000});
  assert.equal(await page.locator('#experiments').getByRole('button',{name:/可见弯曲方向反转 · 首次/}).count(),0);
  await page.waitForFunction(()=>[...document.querySelectorAll('#experiments p')].some(e=>e.textContent.startsWith('共用时间轴')),{},{timeout:120000});
  await page.locator('#experiments').getByRole('button',{name:/目标弯曲投影接近拉直 · 首次/}).first().click();
  const times=await page.locator('#target iframe, #experiments iframe').evaluateAll(frames=>frames.map(f=>f.contentWindow.characterPlayerState.time));
  assert.equal(times.length,2);assert.ok(Math.abs(times[0]-times[1])<.001);assert.deepEqual(errors,[]);
  await fs.mkdir('../tmp/m4-motion-center/knee-check-v1',{recursive:true});
  await page.screenshot({path:'../tmp/m4-motion-center/knee-check-v1/screen.png',fullPage:true});
  console.log(JSON.stringify({passed:true,times,errors}));
}finally{await browser.close();}
