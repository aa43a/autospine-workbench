// Count explicit current decisions separately from fixed-baseline acceptance.
// The same candidate can appear through both view and policy inventories.
export function independentAcceptance(snapshot){
  const candidates=new Map();
  const fixed=new Set(snapshot.rows.map(r=>`${r.job_id}:${r.artifact_sha256}:`));
  function record(row,parent){
    const job=row.job_id||parent,artifact=row.artifact_sha256;
    if(!job||!artifact)return;
    const key=`${job}:${artifact}:${row.registration_sha256||''}`;
    if(fixed.has(key))return;
    const review=row.review;
    const valid=row.status==='verified'&&review?.current_applies===true
      &&['accepted','accepted_with_exceptions'].includes(review.current?.decision);
    const signature=JSON.stringify([valid,review?.revision,review?.evidence_sha256,
      review?.current?.decision]);
    const previous=candidates.get(key);
    candidates.set(key,{valid,signature,conflict:previous?.conflict===true
      ||Boolean(previous&&previous.signature!==signature)});
  }
  function related(family,parent){
    if(family?.status==='verified')for(const row of family.rows||[])record(row,parent);
  }
  for(const base of snapshot.rows){
    if(base.status!=='verified')continue;
    related(base.related,base.job_id);
    for(const name of ['alternatives','policy_variants']){
      const family=base[name];
      if(family?.status!=='verified')continue;
      for(const row of family.rows||[]){
        record(row,base.job_id);
        if(row.status==='verified')related(row.related,row.job_id);
      }
    }
  }
  const rows=[...candidates.values()];
  return {accepted:rows.filter(r=>r.valid&&!r.conflict).length,
    conflicting:rows.filter(r=>r.conflict).length};
}
