// Exercise real source-bound diagnostics without altering a candidate or review.
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const id=process.argv[2];
if(!/^motion-[a-f0-9]{32}$/.test(id||''))throw Error('Exact job id required');
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8918/motions.html#'+id);
  const card=page.locator('#'+id);
  const reply=page.waitForResponse(r=>r.url().endsWith(`/${id}/view/rotation-status.json`),{timeout:120000});
  await card.getByRole('button',{name:'在此检查旋转与绕圈'}).click();
  const response=await reply;assert.equal(response.status(),200,await response.text());
  const report=await response.json();assert.equal(report.animation_modified,false);
  assert.equal(report.authority,'none');assert.ok(report.target.records.length);
  await card.getByRole('link',{name:'完整旋转诊断'}).waitFor();
  assert.ok((await card.textContent()).includes('不能据此判断手掌正反面或轴向扭转'));
  for(const row of report.target.records){
    await card.locator('summary').filter({hasText:row.bone+' ·'}).click();
  }
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,artifact:report.artifact_sha256,
    sourceEvents:report.source.records.reduce((n,r)=>n+r.events.length,0),
    extraTurns:report.target.records.filter(r=>r.extra_turn_suspected).map(r=>r.bone),
    projection:report.projection,clip:report.clip}));
}finally{await browser.close();}
