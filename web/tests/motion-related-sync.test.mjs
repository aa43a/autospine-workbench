import assert from 'node:assert/strict';
import {createRelatedSync} from '../modules/motion-related-sync.js';
const calls=[],clock=createRelatedSync();
const frame=(artifact,duration)=>({contentWindow:{characterPlayerControl:{artifact,seek:t=>{calls.push([artifact,t]);return true;}},characterPlayerState:{duration}}});
clock.seek(1,4);
clock.attach(frame('one',4),'one',{});
clock.attach(frame('two',4),'two',{});
const mismatch={};clock.attach(frame('wrong',4),'expected',mismatch);
assert.match(mismatch.textContent,/候选身份不一致/);
const length={};clock.attach(frame('short',2),'short',length);
assert.match(length.textContent,/时长不同/);
clock.seek(.25,4);
assert.deepEqual(calls,[['one',1],['two',1],['one',.25],['two',.25]]);
clock.clear();clock.seek(3,4);
assert.equal(calls.length,4);
clock.attach(frame('new',4),'new',{});
assert.deepEqual(calls.at(-1),['new',3]);clock.clear();
for(const [time,end,target] of [[NaN,4,4],[1,Infinity,4],[5,4,4],[1,4,NaN]]){
  const guarded=createRelatedSync(),status={},before=calls.length;
  guarded.seek(time,end);guarded.attach(frame('guard',target),'guard',status);
  assert.equal(calls.length,before);assert.match(status.textContent,/同步未启用/);guarded.clear();
}
console.log('Related timeline: exact identities, independent failures, reverse seek and cleanup passed');
