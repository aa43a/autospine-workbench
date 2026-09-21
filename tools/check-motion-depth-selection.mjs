// Exercise real DOM accessibility and strategy reset without submitting jobs.
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({channel:'chrome',headless:true});
try {
  const page=await browser.newPage();
  await page.goto('http://127.0.0.1:8918/motions.html');
  await page.evaluate(async()=>{
    const {createDepthSelection}=await import('/modules/motion-depth-selection.js');
    const host=document.createElement('div');const anchor=document.createElement('button');
    host.id='depth-test';host.append(anchor);document.body.prepend(host);
    window.depthTest=createDepthSelection(anchor);
  });
  const input=page.locator('#depth-test').getByRole('checkbox',{name:'区域深度排序（实验）'});
  assert.equal(await input.isDisabled(),true);
  await page.evaluate(()=>{depthTest.available(true);depthTest.source({job_id:'a',format:'fbx'});});
  await input.check();
  assert.equal((await page.evaluate(()=>depthTest.selection())).depth_review_profile,'external-regional-depth-order-v1');
  await page.evaluate(()=>depthTest.source({job_id:'b',format:'bvh'}));
  assert.equal(await input.isChecked(),false);
  await input.check();
  await page.evaluate(()=>depthTest.source({job_id:'c',format:'npz'}));
  assert.equal(await input.isDisabled(),true);
  assert.deepEqual(await page.evaluate(()=>depthTest.selection()),{});
  const sparse=page.locator('#depth-test').getByRole('checkbox',{name:'稀疏遮挡采样（实验）'});
  assert.equal(await sparse.isDisabled(),true);
  await page.evaluate(()=>depthTest.available(true,true));await sparse.check();
  assert.equal((await page.evaluate(()=>depthTest.selection())).depth_review_profile,'external-arm-torso-depth-sparse-v1-experiment');
  await page.evaluate(()=>depthTest.source({job_id:'d',format:'fbx'}));
  assert.equal(await sparse.isChecked(),false);await input.check();await sparse.check();
  assert.equal(await page.evaluate(()=>{try{depthTest.selection();return false;}catch{return true;}}),true);
  await page.evaluate(()=>depthTest.source(null));assert.equal(await sparse.isDisabled(),true);
  assert.deepEqual(await page.evaluate(()=>depthTest.selection()),{});
  console.log(JSON.stringify({passed:true,sourceReset:true,regionalNpzDisabled:true,sparseNpzEnabled:true,conflictGuard:true}));
} finally {await browser.close();}
