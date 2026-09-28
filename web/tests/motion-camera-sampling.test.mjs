import test from 'node:test';
import assert from 'node:assert/strict';
import {cameraSchedule,interpolateWorld} from '../modules/motion-camera-sampling.js';
import {sampleYaw} from '../modules/motion-yaw-track.js';
test('camera turns hidden between source frames are sampled and originals retained',()=>{
  const keys=[{time:0,yaw:0},{time:.013579,yaw:360},{time:.028765,yaw:0}],times=[0,.033333,.066667,.1];
  const out=cameraSchedule(times,keys,.1);for(const t of [...times,.013579,.028765])assert.ok(out.includes(t));
  assert.ok(out.length>50);for(let i=1;i<out.length;i++)assert.ok(Math.abs(sampleYaw(keys,out[i])-sampleYaw(keys,out[i-1]))<15);
});
test('world interpolation keeps measurements exact and forbids extrapolation',()=>{
  assert.deepEqual(interpolateWorld([[1,2,3],[3,4,5]],[0,1],[0,.5,1]),[[1,2,3],[2,3,4],[3,4,5]]);
  assert.throws(()=>interpolateWorld([[1],[2]],[0,1],[2]),/extrapolation/);
  assert.throws(()=>cameraSchedule([0,.000001],[{time:0,yaw:0},{time:.000001,yaw:360}],.000001),/resolution/);
});
