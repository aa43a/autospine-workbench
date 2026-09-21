// Real candidate plus explicit simulated stale/unsupported responses; read-only.
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const id=process.argv[2];
if(!/^motion-[a-f0-9]{32}$/.test(id||''))throw Error('Exact job id required');
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8918/motions.html#'+id);
  const card=page.locator('#'+id),button=card.getByRole('button',{name:'在此检查躯干偏斜',exact:true});
  const reply=page.waitForResponse(r=>r.url().endsWith(`/${id}/view/motion-torso-projection.json`));
  await button.click();const response=await reply;assert.equal(response.status(),200);
  const actual=await response.json();
  const panel=card.getByRole('region',{name:'躯干偏斜诊断'});
  await panel.getByRole('link',{name:'完整躯干投影证据'}).waitFor();
  assert.ok((await panel.textContent()).includes('偏斜已应用到实验候选'));
  const slider=panel.getByRole('slider');
  await slider.fill(String(actual.source.records.length-1));await slider.dispatchEvent('input');
  const last=actual.source.records.at(-1);
  assert.equal(await panel.getByRole('link',{name:'打开此时刻的角色动画'}).getAttribute('href'),
    `/api/motions/${id}/view/player.html?time=${last.time}`);
  const route=`**/api/motions/${id}/view/motion-torso-projection.json`;
  await page.route(route,r=>r.fulfill({json:{...actual,skeleton_sha256:'stale'}}));
  await button.click();await panel.getByText('无法检查：候选版本已变化，请刷新任务',{exact:true}).waitFor();
  assert.equal(await panel.getByRole('slider').count(),0);
  await page.unroute(route);
  const missing=structuredClone(actual);delete missing.applied;
  await page.route(route,r=>r.fulfill({json:missing}));
  await button.click();await panel.getByText('无法检查：投影采样证据不完整',{exact:true}).waitFor();
  await page.unroute(route);
  const unsupported=structuredClone(actual);unsupported.applied=false;
  unsupported.source.records[1].reasons=['torso_back_view_requires_artwork'];
  await page.route(route,r=>r.fulfill({json:unsupported}));
  await button.click();await panel.getByRole('button',{name:'定位下一处超范围采样'}).click();
  assert.equal(await panel.getByRole('slider').inputValue(),'1');
  assert.ok((await panel.textContent()).includes('背面朝向，需要对应素材'));
  assert.ok((await panel.textContent()).includes('偏斜未应用，保留原动画诊断'));
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,actualSourceFrames:actual.source.records.length,
    actualSkeleton:actual.skeleton_sha256,simulatedCases:['stale_identity','missing_application','unsupported_source']}));
}finally{await browser.close();}
