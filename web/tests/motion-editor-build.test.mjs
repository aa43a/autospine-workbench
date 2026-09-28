import {test} from 'node:test';
import assert from 'node:assert/strict';
import {fixedBuildRequest} from '../modules/motion-editor-build.js';
const draft=()=>({schema:'autospine.motion-editor-draft/v1',project_id:'alice',character_job_id:'job-1',source_id:'motion-1',
  duration:2,time:1,keys:[{time:0,yaw:45}]});
test('fixed build freezes exact character and shared source camera profile',()=>{
  const body=fixedBuildRequest(draft());assert.equal(body.character_job_id,'job-1');assert.equal(body.projection.yaw_degrees,45);
  assert.equal(body.pose_profile,'constant-view-absolute-pose-hip-center-v1-experiment');assert.equal(body.clip,null);
});
test('never silently drops dynamic rotation or folds a full turn into zero',()=>{
  assert.throws(()=>fixedBuildRequest({...draft(),keys:[{time:0,yaw:0},{time:2,yaw:360}]}),/动态角度/);
  assert.throws(()=>fixedBuildRequest({...draft(),keys:[{time:0,yaw:360}]}),/90/);
});
