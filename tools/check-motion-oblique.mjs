// Synthetic submissions only; all adaptation requests are intercepted in-process.
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
 const page=await browser.newPage();await page.goto('http://127.0.0.1:8918/motions.html');
 const result=await page.evaluate(async()=>{
  const {createTargetControls}=await import('/modules/motion-target-controls.js');
  document.body.innerHTML='<select id="target-project"><option value="">select</option></select><p id="target-status"></p><p id="target-source"></p><input id="contact-correction" type="checkbox" checked><button id="adapt"></button>';
  const calls=[],comparisons=[],releases=new Map();let delayed=false;
  const flush=()=>new Promise(r=>setTimeout(r,0));
  const controls=createTargetControls(async(url,options)=>{
   if(options){calls.push(JSON.parse(options.body));return {};}
   if(url==='/api/motions')return {oblique_target_available:true,oblique_comparison_available:true};
   if(url.endsWith('/compare-oblique')){
    const id=url.split('/')[3];comparisons.push(id);
    if(delayed)await new Promise(r=>releases.set(id,r));
    if(id==='source-e')throw Error('fixture comparison unavailable');
    return {source_job_id:id,recommended_yaw_degrees:id==='source-d'?null:-30,comparison_sha256:'receipt-'+id};
   }
   if(url==='/api/projects')return {projects:[{id:'fixture',name:'fixture'}]};
   return {job:{status:'needs_review',project_id:'fixture',job_id:'character-fixture'}};
  },async()=>{},{clip:()=>null});
  await flush();const project=document.getElementById('target-project');project.value='fixture';project.dispatchEvent(new Event('change'));await flush();
  const source=id=>controls.select({job_id:id,name:id,result:{motion_status:'compiled'}});
  const yaw=document.querySelector('[aria-label="动作投影偏转角"]'),adapt=document.getElementById('adapt');
  const auto=[...document.querySelectorAll('button')].find(b=>b.textContent==='自动选择投影角度');
  source('source-a');const defaultBusy=adapt.disabled;await flush();await adapt.onclick();
  source('source-a');await flush();
  yaw.value='-45';yaw.dispatchEvent(new Event('change'));await adapt.onclick();
  source('source-b');const reset=yaw.value;await adapt.onclick();
  await auto.onclick();await adapt.onclick();
  yaw.value='45';yaw.dispatchEvent(new Event('change'));await adapt.onclick();
  delayed=true;const pending=auto.onclick();const blocked=adapt.disabled;await adapt.onclick();const before=calls.length;
  source('source-c');releases.get('source-b')();await pending;const staleYaw=yaw.value,stillBlocked=adapt.disabled;
  releases.get('source-c')();await flush();await adapt.onclick();
  delayed=false;source('source-d');await flush();const noFit=document.body.textContent.includes('当前角度均未通过');await adapt.onclick();
  source('source-e');await flush();source('source-e');await flush();
  const failureVisible=document.body.textContent.includes('fixture comparison unavailable');
  delayed=true;source('source-f');
  const mode=document.querySelector('[aria-label="新动作默认自动选择合格投影"]');
  mode.checked=false;mode.dispatchEvent(new Event('change'));await adapt.onclick();
  releases.get('source-f')();await flush();const canceledYaw=yaw.value;
  delayed=false;mode.checked=true;mode.dispatchEvent(new Event('change'));await flush();await adapt.onclick();
  delayed=true;source('source-g');
  const pose=document.querySelector('[aria-label="姿态策略"]');
  pose.value='source-pose-post-contact-timeline-v2';pose.dispatchEvent(new Event('change'));
  const poseSuspended=mode.disabled&&yaw.disabled&&auto.disabled&&!adapt.disabled;
  releases.get('source-g')();await flush();await adapt.onclick();
  const poseYaw=yaw.value;
  delayed=false;pose.value='';pose.dispatchEvent(new Event('change'));await flush();await adapt.onclick();
  return {calls,comparisons,defaultBusy,reset,blocked,before,staleYaw,stillBlocked,noFit,failureVisible,canceledYaw,poseSuspended,poseYaw};
 });
 assert.equal(result.defaultBusy,true);
 assert.deepEqual(result.calls[0].projection_selection,{comparison_sha256:'receipt-source-a'});
 assert.equal(result.calls[0].projection.yaw_degrees,-30);
 assert.equal(result.comparisons.filter(x=>x==='source-a').length,1);
 assert.equal(result.calls[1].projection.yaw_degrees,-45);assert.equal('projection_selection' in result.calls[1],false);
 assert.equal(result.reset,'');assert.equal('projection' in result.calls[2],false);
 assert.equal(result.calls[3].projection_selection.comparison_sha256,'receipt-source-b');
 assert.equal('projection_selection' in result.calls[4],false);
 assert.equal(result.blocked,true);assert.equal(result.before,5);assert.equal(result.staleYaw,'');assert.equal(result.stillBlocked,true);
 assert.equal(result.calls[5].projection_selection.comparison_sha256,'receipt-source-c');
 assert.equal(result.noFit,true);assert.equal('projection' in result.calls[6],false);
 assert.equal(result.failureVisible,true);assert.equal(result.comparisons.filter(x=>x==='source-e').length,1);
 assert.equal('projection_selection' in result.calls[7],false);assert.equal(result.canceledYaw,'');
 assert.equal(result.calls[8].projection_selection.comparison_sha256,'receipt-source-f');
 assert.equal(result.poseSuspended,true);assert.equal(result.poseYaw,'');
 assert.equal(result.calls[9].pose_profile,'source-pose-post-contact-timeline-v2');
 assert.equal('projection' in result.calls[9],false);assert.equal('projection_selection' in result.calls[9],false);
 assert.equal('pose_profile' in result.calls[10],false);assert.equal(result.calls[10].projection.yaw_degrees,-30);
 console.log(JSON.stringify({passed:true,checks:21,scope:'synthetic_default_selection_no_real_jobs'}));
}finally{await browser.close();}
