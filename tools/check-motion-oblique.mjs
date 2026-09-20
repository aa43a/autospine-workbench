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
    const calls=[]; let delayed=null, release=null;
    const controls=createTargetControls(async (url, options) => {
      if (options) {calls.push(JSON.parse(options.body)); return {};}
      if (url==='/api/motions') return {oblique_target_available:true,oblique_comparison_available:true};
      if (url.endsWith('/compare-oblique')) {
        const response={source_job_id:url.split('/')[3],recommended_yaw_degrees:-30,comparison_sha256:'receipt'};
        if (delayed) await new Promise(resolve=>{release=resolve;});
        return response;
      }
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
    const automatic=[...document.querySelectorAll('button')].find(b=>b.textContent==='自动选择投影角度');
    await automatic.onclick();
    await document.getElementById('adapt').onclick();
    yaw.value='45'; yaw.dispatchEvent(new Event('change'));
    await document.getElementById('adapt').onclick();
    delayed=true;
    const pending=automatic.onclick();
    controls.select({job_id:'source-c',name:'C',result:{motion_status:'compiled'}});
    release(); await pending;
    const staleReset=yaw.value;
    await document.getElementById('adapt').onclick();
    return {calls,reset,staleReset};
  });
  assert.deepEqual(result.calls[0].projection,{profile:'constant-yaw-source-motion-v1',yaw_degrees:-45});
  assert.equal(result.reset,'');
  assert.equal('projection' in result.calls[1],false);
  assert.deepEqual(result.calls[2].projection_selection,{comparison_sha256:'receipt'});
  assert.equal(result.calls[2].projection.yaw_degrees,-30);
  assert.equal('projection_selection' in result.calls[3],false);
  assert.equal(result.staleReset,'');
  assert.equal('projection_selection' in result.calls[4],false);
  assert.equal('projection' in result.calls[4],false);
  console.log(JSON.stringify({passed:true,cases:['explicit_yaw','source_change_reset','legacy_payload','automatic_receipt','manual_override','stale_response']}));
} finally {await browser.close();}
