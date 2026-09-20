// Synthetic target submissions only; no real jobs or review decisions are changed.
import assert from 'node:assert/strict';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({channel: 'chrome', headless: true});
try {
  const page = await browser.newPage();
  await page.goto('http://127.0.0.1:8918/motions.html');
  const result = await page.evaluate(async () => {
    const {createTargetControls} = await import('/modules/motion-target-controls.js');
    document.body.innerHTML = '<select id="target-project"><option value="">select</option></select>'+
      '<p id="target-status"></p><p id="target-source"></p><input id="contact-correction" type="checkbox" checked><button id="adapt"></button>';
    const calls=[];
    const controls=createTargetControls(async (url, options) => {
      if (options) {calls.push(JSON.parse(options.body)); return {};}
      if (url==='/api/motions') return {oblique_target_available:true};
      if (url==='/api/projects') return {projects:[{id:'fixture',name:'fixture'}]};
      return {job:{status:'needs_review',project_id:'fixture',job_id:'character-fixture'}};
    }, async()=>{}, {clip:()=>null});
    await new Promise(resolve=>setTimeout(resolve,0));
    const project=document.getElementById('target-project');
    project.value='fixture'; project.dispatchEvent(new Event('change'));
    await new Promise(resolve=>setTimeout(resolve,0));
    controls.select({job_id:'source-a',name:'A',result:{motion_status:'compiled'}});
    const yaw=document.querySelector('[aria-label="动作投影偏转角"]');
    yaw.value='-45'; await document.getElementById('adapt').onclick();
    controls.select({job_id:'source-b',name:'B',result:{motion_status:'compiled'}});
    const reset=yaw.value;
    await document.getElementById('adapt').onclick();
    return {calls,reset};
  });
  assert.deepEqual(result.calls[0].projection,{profile:'constant-yaw-source-motion-v1',yaw_degrees:-45});
  assert.equal(result.reset,'');
  assert.equal('projection' in result.calls[1],false);
  console.log(JSON.stringify({passed:true,cases:['explicit_yaw','source_change_reset','legacy_payload']}));
} finally {await browser.close();}
