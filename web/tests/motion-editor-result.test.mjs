import test from 'node:test';
import assert from 'node:assert/strict';
import {resultMatch,resultTrack} from '../modules/motion-editor-result.js';
const keys=[{time:0,yaw:0},{time:1,yaw:360}];
const job={kind:'adapt',status:'succeeded',job_id:'target',project_id:'alice',character_job_id:'character',result:{artifact_sha256:'artifact',projection:{profile:'continuous-yaw-source-camera-v1',keys}}};
const link={target_job_id:'target',artifact_sha256:'artifact',clip:null,duration:1,source_job_id:'source',source_sha256:'raw',motion_identity:{clip_sha256:'clip',bundle_sha256:'bundle'}};
const source={source_sha256:'raw',motion_identity:{...link.motion_identity}};
const identity={project_id:'alice',character_job_id:'character',source_id:'source'};
test('exact result retains full turn and rejects unbound or cropped candidates',()=>{
  assert.deepEqual(resultTrack(job,link),keys);
  assert.throws(()=>resultTrack(job,{...link,artifact_sha256:'other'}));
  assert.throws(()=>resultTrack(job,{...link,clip:{start_frame:1,end_frame:2}}));
});
test('stale draft is distinguished from wrong source or character version',()=>{
  assert.equal(resultMatch(job,link,source,identity,keys,keys),'matching');
  assert.equal(resultMatch(job,link,source,identity,[{time:0,yaw:0}],keys),'draft_changed');
  assert.equal(resultMatch(job,link,source,{...identity,character_job_id:'new'},keys,keys),'different_source');
  assert.equal(resultMatch(job,link,{...source,source_sha256:'changed'},identity,keys,keys),'different_source');
  assert.equal(resultMatch(job,link,{...source,motion_identity:{...source.motion_identity,bundle_sha256:'changed'}},identity,keys,keys),'different_source');
});
