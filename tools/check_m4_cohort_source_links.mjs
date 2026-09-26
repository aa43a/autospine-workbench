// Existing API evidence and pure timeline logic only. No browser or new GPU capture.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {verifyCohortSource} from '../web/modules/motion-cohort-source.js';
import {createCohortSync} from '../web/modules/motion-cohort-sync.js';

const output=process.argv[2];if(!output)throw Error('Provide a new receipt path');
if(output!=='-')try{await fs.access(output);throw Error('Receipt already exists');}catch(e){if(e.code!=='ENOENT')throw e;}
const root='workspace/jobs/motion-intake-v1',origin='http://127.0.0.1:8918';
const digest=raw=>createHash('sha256').update(raw).digest('hex');
async function journals(){
  const values={};
  async function collect(folder){
    let names;try{names=await fs.readdir(folder,{withFileTypes:true});}catch(e){if(e.code==='ENOENT')return;throw e;}
    for(const row of names){
      if(row.isFile()&&/^review-\d{4}\.json$/.test(row.name)){
        const name=path.join(folder,row.name);values[path.relative(root,name).replaceAll('\\','/')]=digest(await fs.readFile(name));
      }else if(row.isDirectory()&&/^[a-f0-9]{64}$/.test(row.name))await collect(path.join(folder,row.name));
    }
  }
  for(const row of await fs.readdir(root,{withFileTypes:true}))if(row.isDirectory()&&/^motion-[a-f0-9]{32}$/.test(row.name)){
    await collect(path.join(root,row.name,'stage-reviews'));
    await collect(path.join(root,row.name,'related-stage-reviews'));
  }
  return values;
}
async function get(url){
  const response=await fetch(origin+url,{signal:AbortSignal.timeout(90000)});
  const value=await response.json();if(!response.ok)throw Error(value.reason_code||String(response.status));return value;
}
function duration(value){
  if(!value||typeof value!=='object')return 0;
  return Math.max(typeof value.time==='number'?value.time:0,...Object.values(value).map(duration));
}
const before=await journals(),pack=JSON.parse(await fs.readFile('web/m4-fixed-cohort.json','utf8'));
const items=pack.groups.flatMap(g=>g.targets.map(t=>({g,t,fixed:true})));
const overview=await get('/api/motions');
for(const job of overview.jobs)if(job.kind==='adapt'&&job.status==='succeeded'&&job.result.clip){
  const link=await get(`/api/motions/${job.job_id}/view/source-link.json`);
  items.push({g:{job_id:link.source_job_id,source_sha256:link.source_sha256,label:'clip'},
    t:{job_id:job.job_id,artifact_sha256:job.result.artifact_sha256,label:job.project_id},fixed:false});
}
const sources=new Map(),rows=[];let mismatchChecks=0;
for(const {g,t,fixed} of items){
  if(!sources.has(g.job_id))sources.set(g.job_id,await get(`/api/motions/${g.job_id}`));
  const source=sources.get(g.job_id),base=`/api/motions/${t.job_id}`;
  const job=await get(base),link=await get(base+'/view/source-link.json');
  const range=verifyCohortSource(source,job,link,g,t.artifact_sha256);
  const skeleton=await get(base+'/view/player-assets/skeleton.json');
  assert.ok(skeleton.animations['external-motion']);
  const targetDuration=duration(skeleton.animations['external-motion']);
  assert.ok(Math.abs(targetDuration-range.duration)<.002,'candidate duration');
  const calls=[],status={},sync=createCohortSync(status);
  const times=[range.start,range.start+range.duration*.75,range.start+range.duration*.25,range.end];
  sync.seek(times[0],range.end);
  try{
    sync.attach({contentWindow:{characterPlayerControl:{artifact:t.artifact_sha256,seek:v=>{calls.push(v);return true;}},
      characterPlayerState:{duration:targetDuration}}},t.artifact_sha256,range);
    for(const time of times.slice(1))sync.seek(time,range.end);
    assert.equal(calls.length,times.length);
    times.forEach((time,i)=>assert.ok(Math.abs(calls[i]-(time-range.start))<.002));
  }finally{sync.clear();}
  assert.throws(()=>verifyCohortSource(source,job,{...link,source_job_id:'different'},g,t.artifact_sha256));mismatchChecks++;
  const preview=await get(base+'/view/source-comparison.json');
  assert.deepEqual(verifyCohortSource(source,job,preview,g,t.artifact_sha256),range);
  assert.ok(preview.preview.frames[0].time<=range.start&&preview.preview.frames.at(-1).time>=range.end-1e-6);
  rows.push({cell:g.label+'/'+t.label,fixed,job_id:t.job_id,artifact_sha256:t.artifact_sha256,
    source_job_id:g.job_id,source_sha256:g.source_sha256,motion_ir_sha256:link.motion_identity.motion_ir_sha256,
    source_start:range.start,source_end:range.end,target_duration:targetDuration,clip:range.clip,
    mapped_source_times:times,mapped_target_times:calls,source_relationship_verified:true});
  console.log(JSON.stringify({cell:rows.at(-1).cell,verified:true}));
}
assert.deepEqual(await journals(),before,'human records must remain unchanged');
const result={profile:'m4-cohort-source-time-binding-v1',checked_at:new Date().toISOString(),
  fixed_candidates:rows.filter(r=>r.fixed).length,clipped_candidates:rows.filter(r=>!r.fixed).length,
  rows,mismatch_checks:mismatchChecks,review_journal_hashes:before,mutations:0,
  scope:'verified_existing_candidate_sources_and_pure_timeline_mapping',
  browser_interaction_verified:false,new_runtime_capture:false,quality_pass_counts_changed:false};
if(output==='-')console.log(JSON.stringify({receipt:result}));
else {await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,JSON.stringify(result,null,2)+'\n',{flag:'wx'});}
console.log(JSON.stringify({output,fixed:result.fixed_candidates,clipped:result.clipped_candidates,journals:Object.keys(before).length}));
