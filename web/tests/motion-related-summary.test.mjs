import assert from 'node:assert/strict';
import {relatedSummary,readRelatedSummary,relatedCounts} from '../modules/motion-related-summary.js';
import {deliveryCounts} from '../modules/motion-cohort-delivery.js';
const baseline='a'.repeat(64),candidate='b'.repeat(64),registration='c'.repeat(64);
const entry={registration_sha256:registration,candidate_sha256:candidate,authority:'none',selected:false,production_authorized:false,
  visual:{artifact_sha256:candidate,decision:'stage_accepted_with_retained_exceptions',technical_override:false,applies_to_other_candidates:false,production_authorized:false}};
const report={baseline_sha256:baseline,authority:'none',rows:[entry]};
assert.equal(relatedSummary(report,baseline)[0].visual,'限定范围阶段接受，保留异常');
assert.deepEqual(relatedSummary({...report,rows:[]},baseline),[]);
assert.throws(()=>relatedSummary(report,candidate));
assert.throws(()=>relatedSummary({...report,rows:[entry,entry]},baseline));
for(const patch of [{selected:true},{candidate_sha256:'../bad'},{production_authorized:true},
  {visual:{...entry.visual,artifact_sha256:baseline}},{visual:{...entry.visual,technical_override:true}}]){
  assert.throws(()=>relatedSummary({...report,rows:[{...entry,...patch}]},baseline));
}
assert.equal(relatedSummary({...report,rows:[{...entry,visual:null}]},baseline)[0].visual,'尚无阶段视觉记录');
assert.equal(relatedSummary({...report,rows:[{...entry,visual:{...entry.visual,decision:'unknown'}}]},baseline)[0].visual,'独立阶段记录，范围见详情');
const loaded=await readRelatedSummary(async()=>report,'job',baseline);
const failed=await readRelatedSummary(async()=>{throw Error('offline');},'job',baseline);
assert.equal(loaded.status,'loaded');assert.equal(failed.status,'unavailable');
assert.equal((await readRelatedSummary(async()=>report,'job',candidate)).status,'unavailable');
const abort=new AbortController();abort.abort();
assert.equal((await readRelatedSummary(async()=>{throw Error('abort');},'job',baseline,abort.signal)).message,'核对已停止');
const before=[{loaded:true,status:'needs_changes',applies:false},{loaded:true,status:'stage_review',applies:false}];
const after=before.map((row,i)=>({...row,related:i?failed:loaded}));
assert.deepEqual(deliveryCounts(after,1),deliveryCounts(before,1));
assert.deepEqual(relatedCounts(after),{checked:1,available:1});
console.log('Related summary: identity, authority, unavailable evidence and unchanged baseline denominators passed');
