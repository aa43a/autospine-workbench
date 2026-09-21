import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8918/motions.html');
  assert.equal((await (await page.request.get('http://127.0.0.1:8918/api/motions')).json()).torso_projection_available,true);
  await page.evaluate(async()=>{
    const {createTorsoSelection}=await import('/modules/motion-torso-selection.js');
    const host=document.createElement('div');host.id='torso-test';const anchor=document.createElement('button');
    host.append(anchor);document.body.prepend(host);window.torsoTest=createTorsoSelection(anchor);
  });
  const input=page.locator('#torso-test').getByRole('checkbox',{name:'躯干投影偏斜（实验）'});
  assert.equal(await input.isDisabled(),true);
  await page.evaluate(()=>{torsoTest.available(true);torsoTest.source({job_id:'a',format:'fbx'});});
  await input.check();
  assert.equal((await page.evaluate(()=>torsoTest.selection({}))).torso_projection_profile,'torso-plane-compensated-deform-v1-experiment');
  assert.equal(await page.evaluate(()=>{try{torsoTest.selection({depth_review_profile:'external-regional-depth-order-v1'});return false;}catch{return true;}}),true);
  await page.evaluate(()=>torsoTest.source({job_id:'b',format:'npz'}));
  assert.equal(await input.isChecked(),false);assert.equal(await input.isDisabled(),false);
  await input.check();await page.evaluate(()=>torsoTest.source(null));
  assert.equal(await input.isDisabled(),true);assert.deepEqual(await page.evaluate(()=>torsoTest.selection({})),{});
  assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,sourceReset:true,conflictGuard:true,npzEnabled:true}));
}finally{await browser.close();}
