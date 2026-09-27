// Read-only evidence collection. A snapshot never accepts or replaces a candidate.
import {verifyCohortSource} from './motion-cohort-source.js';
import {relatedSummary} from './motion-related-summary.js';
import {supportExceptions} from './motion-support-exceptions.js';
const id=/^motion-[a-f0-9]{32}$/,sha=/^[a-f0-9]{64}$/;
const compatible=new Set(['legacy_empty_projection_fields','legacy_empty_diagnostic_fields']);
export function validatePack(value){
  if(value?.version!==1||!sha.test(value.plan_sha256)||!Array.isArray(value.groups)||!value.groups.length||value.groups.length>32)throw Error('复核清单无效');
  const jobs=new Set();let count=0;
  for(const g of value.groups){
    if(!id.test(g.job_id)||!sha.test(g.source_sha256)||typeof g.label!=='string'||g.label.length>100||!Array.isArray(g.targets)||!g.targets.length)throw Error('动作来源清单无效');
    for(const t of g.targets){
      if(!id.test(t.job_id)||!sha.test(t.artifact_sha256)||typeof t.label!=='string'||t.label.length>100||jobs.has(t.job_id))throw Error('角色候选清单无效');
      jobs.add(t.job_id);if(++count>96)throw Error('复核数量超过限制');
    }
  }
  if(value.coverage){const c=value.coverage;
    if(!Number.isInteger(c.expected)||c.expected<1||c.expected>96||c.available!==count||!Array.isArray(c.missing)||c.expected!==count+c.missing.length
      ||c.missing.some(r=>['motion','character','status'].some(k=>typeof r[k]!=='string'||r[k].length>100)))throw Error('固定集覆盖数量无效');
  }
  return value;
}

function verifyReview(review,job,artifact,registration){
  if(review?.job_id!==job||review.artifact_sha256!==artifact||!sha.test(review.evidence_sha256)
      ||review.readiness?.artifact_sha256!==artifact||review.authority!=='none'||review.production_authorized!==false
      ||!Number.isInteger(review.revision)||review.revision<0||typeof review.current_applies!=='boolean'
      ||!Array.isArray(review.readiness.stages))throw Error('阶段检查身份不匹配');
  if(registration&&(review.registration_sha256!==registration||review.readiness.registration_sha256!==registration))throw Error('关联检查身份不匹配');
  const stages=new Set();
  for(const s of review.readiness.stages){if(typeof s.stage!=='string'||stages.has(s.stage))throw Error('检查阶段无效');stages.add(s.stage);}
  const c=review.current;
  if(c&&(c.job_id!==job||c.artifact_sha256!==artifact||c.revision!==review.revision||c.production_authorized!==false
      ||!sha.test(c.evidence_sha256)||registration&&c.registration_sha256!==registration))throw Error('阶段结论身份不匹配');
  if(!c&&(review.revision!==0||review.current_applies))throw Error('阶段结论缺失');
  if(review.current_applies&&c.evidence_sha256!==review.evidence_sha256
      &&(registration||!compatible.has(review.evidence_match)))throw Error('阶段结论证据不匹配');
  return review;
}

export async function collectSupportSnapshot(pack,get,{signal,onProgress=()=>{},now=()=>new Date().toISOString()}={}){
  validatePack(pack);
  const started=now(),sources=new Map(),relatedCache=new Map();
  const check=()=>{if(signal?.aborted)throw Error('核对已停止');};
  const read=async path=>{check();const result=await get(path,signal);check();return result;};
  const source=job=>{if(!sources.has(job))sources.set(job,read('/api/motions/'+job));return sources.get(job);};
  const safe=async work=>{try{return {status:'verified',...await work()};}catch(error){check();return {status:'unavailable',reason:error.message};}};
  async function candidate(jobId,artifact,sourceId,sourceHash,evidenceHash){
    if(!id.test(jobId)||!sha.test(artifact)||!id.test(sourceId))throw Error('候选标识无效');
    const s=await source(sourceId),job=await read('/api/motions/'+jobId);
    if(job.job_id!==jobId)throw Error('候选任务身份不匹配');
    const link=await read(`/api/motions/${jobId}/view/source-link.json`);
    verifyCohortSource(s,job,link,{job_id:sourceId,source_sha256:sourceHash},artifact);
    const review=verifyReview(await read(`/api/motions/${jobId}/stage-review`),jobId,artifact);
    if(evidenceHash&&review.evidence_sha256!==evidenceHash)throw Error('比较后证据已变化，请重新核对');
    return {source_link:link,review,checked_at:now()};
  }
  function related(job,artifact){
    const key=job+':'+artifact;
    if(!relatedCache.has(key))relatedCache.set(key,readRelated(job,artifact));
    return relatedCache.get(key);
  }
  async function readRelated(job,artifact){
    const report=await read(`/api/motions/${job}/view/related-candidates.json`);
    const index=relatedSummary(report,artifact),rows=[];
    for(let i=0;i<index.length;i++){
      const r=index[i],evidence=report.rows[i];
      const verified=await safe(async()=>{
        const review=verifyReview(await read(`/api/motions/${job}/related-candidates/${r.registration}/stage-review`),job,r.artifact,r.registration);
        const previous=evidence.stage_review;
        if(!previous||previous.evidence_sha256!==review.evidence_sha256||previous.revision!==review.revision)throw Error('关联结论在核对期间变化');
        return {evidence,review,checked_at:now()};
      });
      rows.push({registration_sha256:r.registration,artifact_sha256:r.artifact,...verified});
    }
    return {rows,complete:rows.every(r=>r.status==='verified')};
  }
  async function alternatives(g,t,policy=false){
    const report=await read(`/api/motions/${t.job_id}/${policy?'policy-variants':'compare-targets'}`);
    if(policy&&(report.profile!=='motion-policy-variant-inventory-v1'||report.recommended_job_id!==null))throw Error('策略候选清单无效');
    if(report?.source_job_id!==t.job_id||report.authority!=='none'||!sha.test(report.comparison_sha256)
        ||report.identity?.source_sha256!==g.source_sha256||!Array.isArray(report.rows)||report.rows.length>24
        ||typeof report.complete!=='boolean'||!Number.isInteger(report.matching_candidates)
        ||report.matching_candidates<report.rows.length||report.complete&&report.matching_candidates!==report.rows.length)throw Error('替代候选比较身份不匹配');
    const seen=new Set(),rows=[];
    for(const r of report.rows){
      if(!id.test(r.job_id)||!id.test(r.source_job_id)||seen.has(r.job_id))throw Error('替代候选清单无效');
      seen.add(r.job_id);
      if(r.job_id===t.job_id){if(r.status!=='succeeded'||r.artifact_sha256!==t.artifact_sha256)throw Error('比较基线已变化');continue;}
      const verified=r.status!=='succeeded'?{status:'unavailable',reason:'构建状态：'+r.status}:await safe(async()=>{
        if(!sha.test(r.evidence_sha256))throw Error('替代检查证据缺失');
        return candidate(r.job_id,r.artifact_sha256,r.source_job_id,g.source_sha256,r.evidence_sha256);
      });
      if(verified.status==='verified')verified.related=await safe(()=>related(r.job_id,r.artifact_sha256));
      rows.push({job_id:r.job_id,source_job_id:r.source_job_id,artifact_sha256:r.artifact_sha256??null,view:r.view,projection:r.projection,...(policy?{policy_changes:r.policy_changes}:{}),...verified});
    }
    return {comparison_sha256:report.comparison_sha256,identity:report.identity,inventory_complete:report.complete,
      matching_candidates:report.matching_candidates,rows,complete:report.complete&&rows.every(r=>r.status==='verified'
        &&r.related?.status==='verified'&&r.related.complete)};
  }
  const tasks=pack.groups.flatMap(g=>g.targets.map(t=>({g,t}))),rows=new Array(tasks.length);let cursor=0,finished=0;
  async function worker(){while(cursor<tasks.length){
    check();const i=cursor++,{g,t}=tasks[i];
    const progress=phase=>onProgress({finished,total:tasks.length,label:g.label+' / '+t.label,phase});
    progress('核对固定候选与验收');
    const verified=await safe(()=>candidate(t.job_id,t.artifact_sha256,g.job_id,g.source_sha256));
    const row={motion:g.label,character:t.label,source_job_id:g.job_id,source_sha256:g.source_sha256,
      job_id:t.job_id,artifact_sha256:t.artifact_sha256,...verified};
    if(row.status==='verified'){
      progress('核对独立改进记录');
      row.related=await safe(()=>related(t.job_id,t.artifact_sha256));
      progress('核对已有替代视角');
      row.alternatives=await safe(()=>alternatives(g,t));
      progress('核对不同策略候选');
      row.policy_variants=await safe(()=>alternatives(g,t,true));
    }
    rows[i]=row;finished++;progress('此项读取完成');
  }}
  await Promise.all([worker(),worker()]);check();
  const snapshot={schema:'autospine.motion-support-snapshot/v1',plan_sha256:pack.plan_sha256,started_at:started,finished_at:now(),
    coverage_declared:Boolean(pack.coverage),expected:tasks.length+(pack.coverage?.missing.length||0),rows,
    missing:structuredClone(pack.coverage?.missing||[]),authority:'none',production_authorized:false,
    limitations:['existing_evidence_only_no_new_capture','per_record_read_times_not_atomic','fixed_source_character_and_clip_only',
      'independent_candidates_do_not_replace_baseline','unverified_is_not_pass','human_acceptance_does_not_override_technical_failures',
      'unregistered_local_experiments_not_in_inventory']};
  snapshot.exception_index=supportExceptions(snapshot);
  return snapshot;
}
