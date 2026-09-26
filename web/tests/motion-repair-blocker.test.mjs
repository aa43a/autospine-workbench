import assert from 'node:assert/strict';
import {test} from 'node:test';
import {appendRepairBlocker,fixedLegReason} from '../modules/motion-repair-blocker.js';
import {jobStatus} from '../modules/motion-job-status.js';

// Component logic; no browser, pixels or layout verification.
class Node{
  constructor(){this.children=[];this.textContent='';}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=items;this.textContent='';}
  setAttribute(){}
}
globalThis.document={createElement:()=>new Node()};
const job={job_id:'motion-failed',kind:'adapt',status:'failed',reason_code:fixedLegReason};
const report={job_id:job.job_id,reason_code:fixedLegReason,candidate_generated:false,slot:'leg',
  failed_triangles:2,sample_count:129,failure_observations:30,parent_job_id:'motion-parent',
  examples:[{triangle:7,time:.5,setup_ratio:.4,projected_ratio:1}]};

test('failed job has readable reason and read-only original candidate locator',async()=>{
  const calls=[];globalThis.fetch=async(...args)=>{calls.push(args);return {ok:true,json:async()=>report};};
  const parent=new Node();appendRepairBlocker(parent,job);await parent.children[0].onclick();
  assert.equal(calls[0][0],'/api/motions/motion-failed/view/repair-blocker.json');
  assert.equal(calls[0][1].method,undefined);
  const section=parent.children[1];assert.match(section.children[0].textContent,/2 个固定三角形.*30 次/);
  assert.match(section.children[1].textContent,/没有生成新候选/);
  assert.equal(section.children[2].children[0].href,'/api/motions/motion-parent/view/player.html?time=0.5');
  assert.match(jobStatus(job,{}, {},{}).detail,/未生成候选/);
});

test('unrelated failure and successful jobs do not fetch blocker; stale report rejected',async()=>{
  const parent=new Node();appendRepairBlocker(parent,{...job,status:'succeeded'});
  appendRepairBlocker(parent,{...job,reason_code:'other'});assert.equal(parent.children.length,0);
  appendRepairBlocker(parent,job);
  globalThis.fetch=async()=>({ok:true,json:async()=>({...report,job_id:'other'})});
  await parent.children[0].onclick();assert.match(parent.children[1].textContent,/身份不匹配/);
  assert.equal(parent.children[1].children.length,0);assert.equal(parent.children[0].disabled,false);
});
