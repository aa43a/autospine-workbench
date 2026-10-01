import test from 'node:test';
import assert from 'node:assert/strict';
import {resultMatch,resultTrack,windComparisonDelta,windComparisonCrop,windPixelDifference} from '../modules/motion-editor-result.js';
const keys=[{time:0,yaw:0},{time:1,yaw:360}];
const job={kind:'adapt',status:'succeeded',job_id:'target',project_id:'alice',character_job_id:'character',result:{artifact_sha256:'artifact',projection:{profile:'continuous-yaw-source-camera-v1',keys}}};
const link={target_job_id:'target',artifact_sha256:'artifact',clip:null,duration:1,source_job_id:'source',source_sha256:'raw',motion_identity:{clip_sha256:'clip',bundle_sha256:'bundle'}};
const source={source_sha256:'raw',motion_identity:{...link.motion_identity}};
const identity={project_id:'alice',character_job_id:'character',source_id:'source'};

test('wind comparison uses matching material vertices and one crop for both images',()=>{
  const a=new Map([['hair',[0,0,10,20]]]),b=new Map([['hair',[3,4,10,20]]]);
  assert.equal(windComparisonDelta(a,b),5);
  assert.equal(windComparisonDelta(a,a),0);
  const bounds={left:-50,bottom:-50,width:100,height:100};
  assert.deepEqual(windComparisonCrop(bounds,[]),{x:0,y:0,width:100,height:100});
  const crop=windComparisonCrop(bounds,[...a.values(),...b.values()]);
  assert.ok(crop.x>=0&&crop.y>=0&&crop.x+crop.width<=100&&crop.y+crop.height<=100);
  assert.ok(crop.width<100&&crop.height<100);
});
test('visible pixel comparison ignores RGB hidden behind transparency and counts silhouette movement',()=>{
  const a=new Uint8ClampedArray([255,0,0,0, 255,255,255,255, 80,90,100,255]);
  const b=new Uint8ClampedArray([0,255,0,0, 255,255,255,0, 82,91,101,255]);
  assert.equal(windPixelDifference(a,b),1);
  assert.equal(windPixelDifference(a,a),0);
  assert.throws(()=>windPixelDifference(a,b.slice(4)),/尺寸/);
});

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

test('historical front or side bodies load only with explicit verified source view',()=>{
  const fixed={...job,result:{...job.result,projection:null}};
  assert.deepEqual(resultTrack(fixed,{...link,source_view:'front'}),[{time:0,yaw:0}]);
  assert.deepEqual(resultTrack(fixed,{...link,source_view:'side'}),[{time:0,yaw:90}]);
  assert.throws(()=>resultTrack(fixed,link));
  assert.equal(resultMatch(fixed,link,source,identity,[{time:0,yaw:0}],[{time:0,yaw:0}]),'matching');
});
