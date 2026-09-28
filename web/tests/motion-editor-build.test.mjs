import {test} from 'node:test';
import assert from 'node:assert/strict';
import {fixedBuildRequest,editorBuildRequest} from '../modules/motion-editor-build.js';
const draft=()=>({schema:'autospine.motion-editor-draft/v1',project_id:'alice',character_job_id:'job-1',source_id:'motion-1',
  duration:2,time:1,keys:[{time:0,yaw:45}]});

test('projected grid remains explicit even for a fixed camera',()=>{
  const profile='camera-world-projected-adaptive-v2';
  const body=editorBuildRequest({...draft(),sampling_profile:profile});
  assert.equal(body.projection.sampling_profile,profile);
  assert.equal(body.projection.profile,'continuous-yaw-source-camera-v1');
  assert.equal(body.contact_correction,false);
});
test('fixed build freezes exact character and shared source camera profile',()=>{
  const body=fixedBuildRequest(draft());assert.equal(body.character_job_id,'job-1');assert.equal(body.projection.yaw_degrees,45);
  assert.equal(body.pose_profile,'constant-view-absolute-pose-hip-center-v1-experiment');assert.equal(body.clip,null);
});
test('fixed and projected builds carry an independent copy of layer corrections',()=>{
  const layer_edits={profile:'slot-world-affine-v1',transforms:[{slot:'arm',dx:8,dy:3,rotation:10,scaleX:1,scaleY:1}],draw_order:[]};
  for(const sampling_profile of [null,'camera-world-projected-adaptive-v2']){
    const value={...draft(),layer_edits,...(sampling_profile?{sampling_profile}:{})};
    const body=editorBuildRequest(value);assert.deepEqual(body.layer_edits,layer_edits);
    body.layer_edits.transforms[0].dx=20;assert.equal(layer_edits.transforms[0].dx,8);
  }
});
test('never silently drops dynamic rotation or folds a full turn into zero',()=>{
  assert.throws(()=>fixedBuildRequest({...draft(),keys:[{time:0,yaw:0},{time:2,yaw:360}]}),/动态角度/);
  assert.throws(()=>fixedBuildRequest({...draft(),keys:[{time:0,yaw:360}]}),/90/);
});
test('dynamic submission freezes the full track and prevents stationary screen locks',()=>{
  const value={...draft(),keys:[{time:0,yaw:0},{time:2,yaw:360}]};
  const body=editorBuildRequest(value);assert.deepEqual(body.projection.keys,value.keys);
  assert.equal(body.pose_profile,'continuous-yaw-source-camera-v1');assert.equal(body.contact_correction,false);
  assert.equal(body.moving_ankle_profile,'continuous-camera-ankle-displacement-v1');
  value.keys[1].yaw=720;assert.equal(body.projection.keys[1].yaw,360);
  assert.equal(editorBuildRequest({...draft(),keys:[{time:0,yaw:360}]}).projection.keys[0].yaw,360);
  assert.deepEqual(editorBuildRequest(draft()),fixedBuildRequest(draft()));
  const adaptive=editorBuildRequest({...value,sampling_profile:'camera-world-linear-adaptive-v1'});
  assert.equal(adaptive.projection.sampling_profile,'camera-world-linear-adaptive-v1');
});
