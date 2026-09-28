// A review refresh may update a decision, never the evidence it evaluated.
export function matchingReviewRows(snapshot,job,registration=null){
  const matches=[];
  function visit(row,parent){
    if(row.status!=='verified')return;
    const owner=row.job_id||parent;
    if(owner===job&&(row.registration_sha256||null)===registration)matches.push(row);
    for(const key of ['related','alternatives','policy_variants']){
      const family=row[key];
      if(family?.status==='verified')for(const child of family.rows||[])visit(child,owner);
    }
  }
  for(const row of snapshot.rows)visit(row,null);
  return matches;
}

export function applyReviewRefresh(matches,review,job,registration,time){
  if(!matches.length)throw Error('candidate_not_in_verified_snapshot:'+job);
  for(const row of matches){
    if(review.job_id!==job||review.artifact_sha256!==row.artifact_sha256
      ||(review.registration_sha256||null)!==registration
      ||(review.readiness?.registration_sha256||null)!==registration
      ||review.evidence_sha256!==row.review.evidence_sha256
      ||JSON.stringify(review.readiness)!==JSON.stringify(row.review.readiness)
      ||review.revision<row.review.revision||review.authority!=='none'||review.production_authorized!==false
      ||!review.current_applies||review.current?.artifact_sha256!==row.artifact_sha256
      ||review.current?.job_id!==job||(review.current?.registration_sha256||null)!==registration
      ||review.current?.production_authorized!==false
      ||!['accepted','accepted_with_exceptions','rejected','revoked'].includes(review.current?.decision)
      ||review.current?.evidence_sha256!==review.evidence_sha256
      ||review.current?.revision!==review.revision)throw Error('review_evidence_changed:'+job);
  }
  for(const row of matches){row.review=structuredClone(review);row.review_checked_at=time;}
}
