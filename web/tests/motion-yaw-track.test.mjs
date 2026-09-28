import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {sampleYaw,validateYawTrack,yawSurfaceWarning} from '../modules/motion-yaw-track.js';
test('browser and backend use the same unwrapped camera contract',()=>{
  const fixture=JSON.parse(fs.readFileSync(new URL('../../tests/fixtures/camera-track-v1.json',import.meta.url)));
  for(const row of fixture.cases){const keys=validateYawTrack(row.keys,row.duration);
    for(const [time,yaw] of row.samples)assert.ok(Math.abs(sampleYaw(keys,time)-yaw)<1e-10);}
});
test('a full turn remains a full turn, including backward seeks',()=>{
  const keys=validateYawTrack([{time:0,yaw:0},{time:2,yaw:360}],2);
  assert.equal(sampleYaw(keys,1),180);assert.equal(sampleYaw(keys,2),360);
  assert.equal(sampleYaw(keys,.5),90);assert.equal(sampleYaw(keys,0),0);
});
test('unwrapped crossing retains direction instead of 180 degree jump',()=>{
  const keys=validateYawTrack([{time:0,yaw:350},{time:1,yaw:370}],1);
  assert.equal(sampleYaw(keys,.5),360);assert.equal(sampleYaw(keys,1),370);
  assert.equal(sampleYaw([{time:0,yaw:30},{time:1,yaw:-330}],.5),-150);
});
test('invalid and duplicate times or non-finite angles are refused',()=>{
  for(const keys of [[{time:1,yaw:0}],[{time:0,yaw:NaN}],[{time:0,yaw:0},{time:0,yaw:360}],
    [{time:0,yaw:0},{time:3,yaw:90}],[{time:0,yaw:3601}]])assert.throws(()=>validateYawTrack(keys,2));
});
test('missing rear surface remains explicit after full rotations',()=>{
  assert.match(yawSurfaceWarning(180),/背向/);assert.match(yawSurfaceWarning(540),/背向/);
  assert.match(yawSurfaceWarning(90),/侧向/);assert.match(yawSurfaceWarning(360),/正面/);
});
