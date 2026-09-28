import {validateJointCandidate,validateJointConfig} from './motion-joint-editor-state.js';

const sha=value=>/^[a-f0-9]{64}$/.test(value);
const sorted=value=>Array.isArray(value)?value.map(sorted):value&&typeof value==='object'?
  Object.fromEntries(Object.keys(value).sort().map(key=>[key,sorted(value[key])])):value;
const equal=(a,b)=>JSON.stringify(sorted(a))===JSON.stringify(sorted(b));

export function validateJointResultRestore(job,report,meta,provenance,hashes){
  validateJointCandidate(job);const result=job.result;
  if(!meta||!result.joint_animation_profile||report?.schema!=='autospine.joint-animation/v1'||
      report.profile!==result.joint_animation_profile||provenance?.profile!==report.profile||
      job.project_id!==meta.project_id||job.character_job_id!==meta.character_job_id)
    throw Error('联合候选与当前角色身份不一致，未恢复参数。');
  if(result.joint_parent_job_id!==meta.parent_job_id||result.joint_parent_artifact_sha256!==meta.artifact_sha256||
      provenance.parent_job_id!==meta.parent_job_id||provenance.parent_artifact_sha256!==meta.artifact_sha256||
      provenance.animation!==meta.animation||report.animation!==meta.animation||
      provenance.duration!==meta.duration||report.duration!==meta.duration)
    throw Error('联合候选使用不同的身体版本或时间轴，未恢复参数。');
  if(!sha(report.config_sha256)||report.config_sha256!==result.joint_config_sha256||
      report.config_sha256!==provenance.config_sha256||!equal(report.config,provenance.config))
    throw Error('联合候选参数与冻结请求不一致，未恢复参数。');
  const source=provenance.source_provenance;
  if(!source||!sha(source.parent_request_sha256)||!equal(source,meta.source_provenance)||
      !equal(source,result.joint_source_provenance)||source.parent_job_id!==meta.parent_job_id||
      source.artifact_sha256!==meta.artifact_sha256||
      (source.registration_sha256??null)!==(meta.registration_sha256??null))
    throw Error('联合候选的来源请求或修正版本已变化，未恢复参数。');
  if(!sha(report.parent_skeleton_sha256)||!sha(report.skeleton_sha256)||
      report.parent_skeleton_sha256!==hashes.parent||report.skeleton_sha256!==hashes.joint)
    throw Error('联合候选骨架与原身体骨架校验不一致，未恢复参数。');
  return validateJointConfig(report.config,meta);
}

export async function jointChecksum(url){
  const response=await fetch(url,{cache:'no-store'});
  if(!response.ok)throw Error(`无法读取候选骨架 (${response.status})。`);
  const digest=await crypto.subtle.digest('SHA-256',await response.arrayBuffer());
  return [...new Uint8Array(digest)].map(value=>value.toString(16).padStart(2,'0')).join('');
}
