import assert from 'node:assert/strict';
import {test} from 'node:test';
import {verifyCohortSource,sameSourceRange} from '../modules/motion-cohort-source.js';

export function fixture(clip=null) {
  const source={job_id:'source',status:'succeeded',source_sha256:'bytes',result:{
    motion:{bundle_sha256:'bundle',motion_ir_sha256:'motion',source_kind:'bvh'},
    fps:30,frame_count:121,duration_seconds:4}};
  const job={job_id:'target',kind:'adapt',status:'succeeded',result:{artifact_sha256:'asset',clip}};
  const link={authority:'none',target_job_id:'target',source_job_id:'source',source_sha256:'bytes',
    artifact_sha256:'asset',motion_identity:{...source.result.motion},clip,
    source_fps:30,source_frame_count:121,source_duration:4,
    source_start:clip?clip.start_frame/30:0,source_end:clip?clip.end_frame/30:4};
  link.duration=link.source_end-link.source_start;
  const group={job_id:'source',source_sha256:'bytes'};
  return {source,job,link,group};
}
const verify=f=>verifyCohortSource(f.source,f.job,f.link,f.group,'asset');

test('exact whole and clipped source ranges survive roundtrip',()=>{
  const whole=fixture(),cut=fixture({start_frame:30,end_frame:60});
  assert.deepEqual(verify(whole),{start:0,end:4,duration:4,clip:null,fps:30,frameCount:121});
  assert.deepEqual(verify(cut),{start:1,end:2,duration:1,clip:cut.job.result.clip,fps:30,frameCount:121});
  assert.equal(sameSourceRange(verify(whole),verify(cut)),false);
  assert.equal(sameSourceRange(verify(cut),{...verify(cut)}),true);
  assert.equal(sameSourceRange(verify(cut),{...verify(cut),start:2,end:3}),false); // Same duration, different content.
  assert.equal(sameSourceRange(verify(cut),{...verify(cut),fps:60}),false); // Same seconds, different source frames.
});

test('two individually valid jobs cannot be presented as a verified pair',()=>{
  for(const mutate of [f=>f.link.source_job_id='other',f=>f.link.source_sha256='different',
    f=>f.link.motion_identity.motion_ir_sha256='different-map',f=>delete f.link.motion_identity.bundle_sha256,
    f=>f.link.target_job_id='other',f=>f.job.result.artifact_sha256='changed',
    f=>f.source.job_id='other',f=>f.link.authority='accepted']) {
    const f=fixture();mutate(f);assert.throws(()=>verify(f));
  }
});

test('equal durations do not hide shifted clips or invalid sampling',()=>{
  for(const mutate of [f=>{f.link.source_start=2;f.link.source_end=3;},
    f=>f.link.clip={start_frame:60,end_frame:90},f=>f.link.duration=NaN,
    f=>f.link.source_fps=60,f=>f.link.source_frame_count=60,
    f=>f.link.source_duration=Infinity,f=>f.link.source_end=5]) {
    const f=fixture({start_frame:30,end_frame:60});mutate(f);assert.throws(()=>verify(f));
  }
});
