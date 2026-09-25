import assert from 'node:assert/strict';
import {stageSummary} from '../modules/motion-stage-summary.js';
const state = {artifact_sha256:'a', readiness:{artifact_sha256:'a',status:'needs_changes',
  stages:[{stage:'Runtime',status:'sampled_pass'},{stage:'遮挡',status:'needs_changes'}]},
  current_applies:true,current:{decision:'accepted_with_exceptions'}};
const text=stageSummary(state,'a');
assert.match(text,/需处理技术异常/);
assert.match(text,/待处理或未验证：遮挡/);
assert.match(text,/视觉：阶段可接受，保留异常/);
assert.doesNotMatch(text,/技术通过且阶段接受/);
assert.match(stageSummary({...state,current_applies:false},'a'),/历史结论（当前证据不适用）/);
assert.match(stageSummary({...state,current:null},'a'),/尚未阶段验收/);
assert.throws(()=>stageSummary(state,'b'),/身份不匹配/);
assert.throws(()=>stageSummary({...state,readiness:{...state.readiness,artifact_sha256:'b'}},'a'),/身份不匹配/);
assert.match(stageSummary(null,'a'),/尚未核对/);
console.log('Stage summary: independent technical/visual status and identity checks passed');
