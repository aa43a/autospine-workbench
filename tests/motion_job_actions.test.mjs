import assert from 'node:assert/strict';
import {jobAction,successorId} from '../web/modules/motion-job-actions.js';
for(const status of ['canceled','interrupted','failed','succeeded','outdated']) {
  assert.match(jobAction({kind:'adapt',status}).label,/重新构建角色动作/);
  assert.match(jobAction({kind:'generate',status}).label,/重新生成动作/);
  assert.match(jobAction({kind:'import',status}).label,/重新解析来源/);
  assert.equal(jobAction({kind:'adapt',status}).action,'retry');
}
assert.deepEqual(jobAction({status:'running',cancel_requested:true}),
  {action:'cancel',label:'正在停止任务…',disabled:true});
assert.equal(jobAction({status:'pending'}).action,'cancel');
const old='motion-'+'a'.repeat(32), next='motion-'+'b'.repeat(32);
assert.equal(successorId(old,{job_id:next}),next);
for(const result of [{},{job_id:old},{job_id:'javascript:alert(1)'}])assert.throws(()=>successorId(old,result));
console.log('Job labels, cancel state and retry identity checks passed');
