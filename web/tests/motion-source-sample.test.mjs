import {test} from 'node:test';
import assert from 'node:assert/strict';
import {sampleSourceFrame} from '../modules/motion-source-sample.js';
test('same-time interpolation and reverse seeks preserve source observations',()=>{
  const frames=[{time:0,frame:0,joints:[[0,0,0]]},{time:1,frame:1,joints:[[10,2,-4]]}];
  assert.deepEqual(sampleSourceFrame(frames,.75).joints,[[7.5,1.5,-3]]);
  assert.deepEqual(sampleSourceFrame(frames,.25).joints,[[2.5,.5,-1]]);
  assert.equal(sampleSourceFrame(frames,1),frames[1]);assert.deepEqual(frames[0].joints,[[0,0,0]]);
  assert.throws(()=>sampleSourceFrame(frames,NaN));
});
