import test from 'node:test';
import assert from 'node:assert/strict';
import {resultMatch,resultTrack} from '../modules/motion-editor-result.js';
const keys=[{time:0,yaw:0},{time:1,yaw:360}];
const job={kind:'adapt',status:'succeeded',job_id:'target',project_id:'alice',character_job_id:'character',result:{artifact_sha256:'artifact',projection:{profile:'continuous-yaw-source-camera-v1',keys}}};
const link={target_job_id:'target',artifact_sha256:'artifact',clip:null,duration:1,source_job_id:'source',source_sha256:'raw',motion_identity:{clip_sha256:'clip',bundle_sha256:'bundle'}};
const source={source_sha256:'raw',motion_identity:{...link.motion_identity}};
const identity={project_id:'alice',character_job_id:'character',source_id:'source'};

test('last frame rational time agrees with MotionIR microsecond keys',()=>{
  const candidate=structuredClone(job);candidate.result.projection.keys=[{time:0,yaw:0},{time:.966667,yaw:360}];
  assert.deepEqual(resultTrack(candidate,{...link,duration:29/30}),candidate.result.projection.keys);
  candidate.result.projection.keys[1].time=.966668;
  assert.throws(()=>resultTrack(candidate,{...link,duration:29/30}));
});
test('exact result retains full turn and rejects unbound or cropped candidates',()=>{
  assert.deepEqual(resultTrack(job,link),keys);
  assert.throws(()=>resultTrack(job,{...link,artifact_sha256:'other'}));
  assert.throws(()=>resultTrack(job,{...link,clip:{start_frame:1,end_frame:2}}));
});
test('stale draft is distinguished from wrong source or character version',()=>{
  assert.equal(resultMatch(job,link,source,identity,keys,keys),'matching');
  assert.equal(resultMatch(job,link,source,identity,[{time:0,yaw:0}],keys),'draft_changed');
  assert.equal(resultMatch(job,link,source,{...identity,sampling_profile:'camera-world-linear-adaptive-v1'},keys,keys),'draft_changed');
  assert.equal(resultMatch(job,link,source,{...identity,character_job_id:'new'},keys,keys),'different_source');
  assert.equal(resultMatch(job,link,{...source,source_sha256:'changed'},identity,keys,keys),'different_source');
  assert.equal(resultMatch(job,link,{...source,motion_identity:{...source.motion_identity,bundle_sha256:'changed'}},identity,keys,keys),'different_source');
});
test('editing only a layer marks a loaded result stale; exact layer restore matches',()=>{
  const layer_edits={profile:'slot-world-affine-v1',transforms:[{slot:'arm',dx:3,dy:0,rotation:0,scaleX:1,scaleY:1}],draw_order:[]};
  const selection={...identity,layer_edits};
  assert.equal(resultMatch(job,link,source,selection,keys,keys),'draft_changed');
  const edited={...job,result:{...job.result,layer_edits}};
  assert.equal(resultMatch(edited,link,source,selection,keys,keys),'matching');
  assert.equal(resultMatch(edited,link,source,identity,keys,keys),'draft_changed');
});
