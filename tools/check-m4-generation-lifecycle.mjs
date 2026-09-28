// Opt-in real local model/UI probe. Creates one job and one retry; retains both.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome]=process.argv.slice(2),base='http://127.0.0.1:8918';
const get=async tail=>{const r=await fetch(base+'/api/motions'+tail);assert.ok(r.ok);return r.json();};
const inventory=await get('');
assert.ok(!inventory.jobs.some(j=>['pending','running'].includes(j.status)),'Existing active jobs; probe not started');
assert.equal(inventory.kimodo_generation,'configured');await fs.mkdir(output);
const report={profile:'real-generation-browser-lifecycle-v1',events:[],jobs:[],passed:false,
  parameters:{prompt:'A person stands still and breathes gently',duration_seconds:1,seed:20260928,diffusion_steps:10,view:'front'}};
const persist=()=>fs.writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n');
await persist();
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true});
let ownActive=null;
try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(base+'/motions.html');await page.locator('#generate').waitFor();
  await page.waitForFunction(()=>!document.getElementById('generate').disabled);
  for(const [id,value] of Object.entries({prompt:report.parameters.prompt,duration:1,seed:20260928,steps:10}))await page.locator('#'+id).fill(String(value));
  await page.locator('#generation-view').selectOption('front');
  const response=page.waitForResponse(r=>r.url()===base+'/api/motions/generate'&&r.request().method()==='POST');
  await page.locator('#generate').click();const created=await response;assert.ok(created.ok());
  const first=(await created.json()).job_id;assert.match(first,/^motion-[a-f0-9]{32}$/);
  ownActive=first;report.jobs.push(first);await persist();
  async function until(job,predicate){
    const deadline=Date.now()+600000;let prior='';
    while(Date.now()<deadline){
      const current=await get('/'+job),key=JSON.stringify([current.status,current.step,current.cancel_requested]);
      if(key!==prior){report.events.push({job_id:job,at:new Date().toISOString(),status:current.status,step:current.step,activity:current.activity});prior=key;await persist();console.log(job+' '+key);}
      if(predicate(current))return current;
      if(!['pending','running'].includes(current.status))throw Error('Unexpected terminal state '+JSON.stringify(current));
      await new Promise(resolve=>setTimeout(resolve,1000));
    }
    throw Error('Probe deadline; see preserved task');
  }
  await until(first,j=>j.status==='running'&&j.step==='generate_motion'&&j.activity?.log_bytes>0);
  await page.locator('#refresh').click();const card=page.locator('#'+first);
  await card.locator('.generation-activity').waitFor();
  report.progress_text=await card.locator('.generation-activity').innerText();
  await card.screenshot({path:path.join(output,'running.png')});
  await card.getByRole('button',{name:'取消任务',exact:true}).click();
  const canceled=await until(first,j=>j.status==='canceled');ownActive=null;
  report.canceled=canceled;await persist();await page.reload();
  const retryResponse=page.waitForResponse(r=>r.url()===base+`/api/motions/${first}/retry`&&r.request().method()==='POST');
  await page.locator('#'+first).getByRole('button',{name:'重新生成动作（保留旧记录）',exact:true}).click();
  const retried=await retryResponse;assert.ok(retried.ok());const second=(await retried.json()).job_id;
  assert.notEqual(second,first);assert.match(second,/^motion-[a-f0-9]{32}$/);
  ownActive=second;report.jobs.push(second);await persist();
  await page.waitForFunction(id=>location.hash==='#'+id,second);
  const result=await until(second,j=>j.status==='succeeded');ownActive=null;
  assert.equal(result.retry_of.job_id,first);assert.equal(result.result.motion_status,'compiled');
  report.result=result;assert.deepEqual(await get('/'+first),canceled);
  await page.reload();
  await page.locator('#'+second).getByRole('button',{name:'查看源动作',exact:true}).click();
  await page.waitForFunction(()=>!document.getElementById('play').disabled);
  await page.locator('#time').evaluate(el=>{el.value=String(Number(el.max)/2);el.dispatchEvent(new Event('input',{bubbles:true}));});
  report.preview_clock=await page.locator('#clock').innerText();
  await page.screenshot({path:path.join(output,'reopened.png')});
  assert.deepEqual(errors,[]);report.errors=errors;report.passed=true;
  report.scope='real_UI_generation_progress_cancel_independent_retry_reload_and_source_preview_not_character_acceptance';
  await persist();console.log('Real generation browser lifecycle passed');
}catch(error){report.error=String(error);await persist();throw error;}
finally{
  // Only stop a still-running job created by this probe, never another user's work.
  if(ownActive){const current=await get('/'+ownActive);if(['pending','running'].includes(current.status)){
    const r=await fetch(base+`/api/motions/${ownActive}/cancel`,{method:'POST',headers:{'Content-Type':'application/json',Origin:base,'X-Autospine-Intent':'pipeline-preview'},body:'{}'});
    report.cleanup_cancel_requested=r.ok;await persist();
  }}
  await browser.close();
}
