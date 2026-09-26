// Related candidates are independent evidence, never a replacement baseline result.
const sha=/^[a-f0-9]{64}$/;
export function relatedSummary(report, artifact) {
  if(!sha.test(artifact)||report?.baseline_sha256!==artifact||report.authority!=='none'
      ||!Array.isArray(report.rows)||report.rows.length>24)throw Error('关联来源不匹配');
  const registrations=new Set();
  return report.rows.map(row=>{
    if(!sha.test(row.registration_sha256)||!sha.test(row.candidate_sha256)
        ||registrations.has(row.registration_sha256)||row.authority!=='none'
        ||row.production_authorized!==false||row.selected!==false)throw Error('关联候选记录无效');
    registrations.add(row.registration_sha256);
    const visual=row.visual;
    if(visual&&(visual.artifact_sha256!==row.candidate_sha256||visual.technical_override!==false
        ||visual.applies_to_other_candidates!==false||visual.production_authorized!==false))throw Error('关联视觉记录不匹配');
    const labels={accepted:'有独立阶段接受记录',accepted_with_exceptions:'阶段接受，保留异常',
      stage_accepted_with_retained_exceptions:'限定范围阶段接受，保留异常',rejected:'视觉需调整',revoked:'阶段记录已撤销'};
    let conclusion=visual?(labels[visual.decision]||'独立阶段记录，范围见详情'):'尚无阶段视觉记录';
    const state=row.stage_review;
    if(state){
      if(state.artifact_sha256!==row.candidate_sha256||state.registration_sha256!==row.registration_sha256
          ||!Number.isInteger(state.revision)||state.revision<0)throw Error('关联阶段记录不匹配');
      if(state.current){
        if(state.current.registration_sha256!==row.registration_sha256||state.current.artifact_sha256!==row.candidate_sha256
            ||state.current.revision!==state.revision||state.current.production_authorized!==false)throw Error('关联阶段记录不匹配');
        const exact=state.current_applies===true&&state.current.evidence_sha256===state.evidence_sha256;
        conclusion=(exact?'':'历史结论，当前证据需复核：')+(labels[state.current.decision]||'未知阶段记录');
      }else if(state.revision!==0||state.current_applies===true)throw Error('关联阶段记录不匹配');
    }
    return {registration:row.registration_sha256,artifact:row.candidate_sha256,
      visual:conclusion};
  });
}

export async function readRelatedSummary(get, job, artifact, signal) {
  try {
    const report=await get(`/api/motions/${job}/view/related-candidates.json`,signal);
    return {status:'loaded',rows:relatedSummary(report,artifact)};
  } catch(error) {
    return {status:'unavailable',rows:[],message:signal?.aborted?'核对已停止':'关联记录尚未核实'};
  }
}

export function relatedCounts(rows) {
  return {checked:rows.filter(r=>r.related?.status==='loaded').length,
    available:rows.filter(r=>r.related?.status==='loaded'&&r.related.rows.length>0).length};
}
