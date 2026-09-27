export const hash=c=>c.repeat(64),job=c=>'motion-'+c.repeat(32);
export function fixture(){
  const sourceId=job('1'),targetId=job('2'),alternativeId=job('3'),sourceHash=hash('a'),asset=hash('b'),evidence=hash('c');
  const pack={version:1,plan_sha256:hash('d'),groups:[{label:'breathing',job_id:sourceId,source_sha256:sourceHash,
    targets:[{label:'alice',job_id:targetId,artifact_sha256:asset}]}],coverage:{expected:2,available:1,missing:[{motion:'walking',character:'alice',status:'failed'}]}};
  const source={job_id:sourceId,status:'succeeded',source_sha256:sourceHash,result:{motion:{motion_ir_sha256:hash('e')},fps:30,frame_count:121,duration_seconds:4}};
  const target=(jid,a)=>({job_id:jid,kind:'adapt',status:'succeeded',result:{artifact_sha256:a,clip:null}});
  const link=(jid,a)=>({authority:'none',target_job_id:jid,artifact_sha256:a,source_job_id:sourceId,source_sha256:sourceHash,
    motion_identity:source.result.motion,source_fps:30,source_frame_count:121,source_duration:4,source_start:0,source_end:4,duration:4,clip:null});
  function review(jid,a){return {job_id:jid,artifact_sha256:a,evidence_sha256:evidence,authority:'none',production_authorized:false,
    revision:1,evidence_match:'exact',current_applies:true,current:{job_id:jid,artifact_sha256:a,evidence_sha256:evidence,revision:1,
      decision:'accepted_with_exceptions',notes:'呼吸阶段可接受，保留技术异常',production_authorized:false},
    readiness:{artifact_sha256:a,status:'needs_changes',stages:['投影','几何','接触','遮挡','Runtime'].map(stage=>({stage,
      status:stage==='遮挡'?'needs_changes':'sampled_pass',explanation:stage==='遮挡'?'同帧遮挡失败':'限定采样'}))}};}
  const registry=new Map([
    [`/api/motions/${sourceId}`,source],[`/api/motions/${targetId}`,target(targetId,asset)],
    [`/api/motions/${targetId}/view/source-link.json`,link(targetId,asset)],[`/api/motions/${targetId}/stage-review`,review(targetId,asset)],
    [`/api/motions/${targetId}/view/related-candidates.json`,{authority:'none',baseline_sha256:asset,rows:[]}],
    [`/api/motions/${targetId}/compare-targets`,{authority:'none',comparison_sha256:hash('f'),source_job_id:targetId,
      identity:{source_sha256:sourceHash},complete:true,matching_candidates:1,rows:[{job_id:targetId,source_job_id:sourceId,status:'succeeded',artifact_sha256:asset,evidence_sha256:evidence}]}],
  ]);
  const calls=[];
  const get=async path=>{calls.push(path);if(!registry.has(path))throw Error('not found: '+path);return structuredClone(registry.get(path));};
  function addAlternative(){
    const a=hash('7');registry.set(`/api/motions/${alternativeId}`,target(alternativeId,a));
    registry.set(`/api/motions/${alternativeId}/view/source-link.json`,link(alternativeId,a));
    registry.set(`/api/motions/${alternativeId}/stage-review`,review(alternativeId,a));
    registry.set(`/api/motions/${alternativeId}/view/related-candidates.json`,{authority:'none',baseline_sha256:a,rows:[]});
    const report=registry.get(`/api/motions/${targetId}/compare-targets`);report.matching_candidates++;
    report.rows.push({job_id:alternativeId,source_job_id:sourceId,status:'succeeded',artifact_sha256:a,evidence_sha256:evidence,view:'side'});
    return alternativeId;
  }
  function addRelated(parentId=targetId){
    const registration=hash('8'),a=hash('9'),state=review(parentId,a);
    state.registration_sha256=registration;state.current.registration_sha256=registration;state.readiness.registration_sha256=registration;
    registry.set(`/api/motions/${parentId}/related-candidates/${registration}/stage-review`,state);
    registry.get(`/api/motions/${parentId}/view/related-candidates.json`).rows.push({registration_sha256:registration,candidate_sha256:a,
      authority:'none',selected:false,production_authorized:false,stage_review:structuredClone(state),sampled_frames:129});
    return registration;
  }
  return {pack,registry,get,calls,sourceId,targetId,asset,sourceHash,evidence,addAlternative,addRelated};
}
