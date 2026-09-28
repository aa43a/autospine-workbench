import test from 'node:test';
import assert from 'node:assert/strict';
import {validateJointResultRestore} from '../modules/motion-joint-editor-restore.js';
import {createJointWorkflow} from '../modules/motion-joint-editor-workflow.js';
const id='motion-'+'1'.repeat(32),jid='motion-'+'2'.repeat(32),hash='a'.repeat(64),output='b'.repeat(64);
function fixture(){
 const config={schema:'autospine.joint-animation-config/v1',fps:30,seed:0,loop:false,face:{enabled:true},hair:{enabled:true},cloth:{enabled:true}};
 const source={parent_job_id:id,artifact_sha256:hash,parent_request_sha256:'c'.repeat(64),registration_sha256:null};
 const meta={parent_job_id:id,artifact_sha256:hash,project_id:'alice',character_job_id:'character-1',source_provenance:source,
  controls:[],defaults:config,animation:'external-motion',duration:3};
 const parent={job_id:id,kind:'adapt',status:'succeeded',result:{artifact_sha256:hash}};
 const job={job_id:jid,kind:'adapt',status:'succeeded',project_id:'alice',character_job_id:'character-1',result:{artifact_sha256:output,
  joint_animation_profile:'joint-face-hair-cloth-v1',joint_parent_job_id:id,joint_parent_artifact_sha256:hash,
  joint_config_sha256:'d'.repeat(64),joint_source_provenance:source}};
 const provenance={profile:'joint-face-hair-cloth-v1',parent_job_id:id,parent_artifact_sha256:hash,animation:'external-motion',duration:3,
  config_sha256:'d'.repeat(64),config,source_provenance:source};
 const report={schema:'autospine.joint-animation/v1',profile:provenance.profile,animation:'external-motion',duration:3,
  config_sha256:provenance.config_sha256,config,parent_skeleton_sha256:'e'.repeat(64),skeleton_sha256:'f'.repeat(64)};
 return {parent,job,report,meta,provenance,hashes:{parent:'e'.repeat(64),joint:'f'.repeat(64)}};
}
test('saved candidate restores exact config and remains current until changed, then builds a new job',async()=>{
 const f=fixture(),inspected=[],writes=[],requests=[];
 const workflow=createJointWorkflow({storage:{getItem:()=>JSON.stringify({job_id:jid,config:{bad:true}}),setItem:(...v)=>writes.push(v)},
  request:async(url,body)=>{requests.push({url,body});return body?{job_id:'motion-'+'3'.repeat(32),status:'queued'}:url.endsWith('/joint-animation')?f.meta:f.provenance;},
  checksum:async url=>url.includes(jid)?f.hashes.joint:f.hashes.parent,inspect:job=>inspected.push(job.job_id),schedule:()=>0,unschedule:()=>{}});
 await workflow.load(f.parent,{restoreTask:false});assert.equal(workflow.state.resultJob,null);
 assert.equal(await workflow.restoreResult(f.job,f.report),true);assert.equal(workflow.state.changed,false);
 assert.equal(workflow.state.resultJob.job_id,jid);assert.deepEqual(inspected,[jid]);
 workflow.change('hair','enabled',false);assert.equal(workflow.state.changed,true);
 await workflow.build();const post=requests.find(r=>r.body);
 assert.equal(post.url,`/api/motions/${id}/joint-animation`);assert.equal(post.body.artifact_sha256,hash);
 assert.equal(post.body.config.hair.enabled,false);assert.equal(f.report.config.hair.enabled,true);
 workflow.close();
});
test('restore rejects wrong role, config, request, parent or skeleton identity',()=>{
 const edits=[f=>f.job.project_id='huiye',f=>f.job.character_job_id='other',f=>f.report.config_sha256='0'.repeat(64),
  f=>f.provenance.config={...f.provenance.config,loop:true},f=>f.hashes.parent='0'.repeat(64),f=>f.hashes.joint='0'.repeat(64),
  f=>f.provenance.source_provenance={...f.provenance.source_provenance,parent_request_sha256:'0'.repeat(64)},
  f=>f.job.result.joint_parent_artifact_sha256='0'.repeat(64)];
 for(const edit of edits){const f=fixture();edit(f);assert.throws(()=>validateJointResultRestore(f.job,f.report,f.meta,f.provenance,f.hashes));}
});
test('a delayed restore cannot overwrite newly selected body or inspect an old result',async()=>{
 const f=fixture();let inspected=0;
 const pending=[];const guarded=createJointWorkflow({storage:{getItem:()=>null,setItem:()=>{}},inspect:()=>inspected++,
  request:async url=>url.endsWith('/joint-animation')?f.meta:f.provenance,checksum:()=>new Promise(r=>pending.push(r))});
 await guarded.load(f.parent);const request=guarded.restoreResult(f.job,f.report);guarded.reset();
 pending[0](f.hashes.parent);pending[1](f.hashes.joint);assert.equal(await request,false);assert.equal(inspected,0);assert.equal(guarded.state.meta,null);
});
