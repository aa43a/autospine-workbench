// Count explicit current decisions separately from fixed-baseline acceptance.
// The same candidate can appear through both view and policy inventories.
function independentRecords(snapshot){
  const candidates=new Map();
  const fixed=new Set(snapshot.rows.map(r=>`${r.job_id}:${r.artifact_sha256}:`));
  function record(row,parent,cell,anchor){
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
    const locations=previous?.locations||[];
    if(!locations.some(r=>r.cell===cell))locations.push({cell,anchor});
    candidates.set(key,{valid,signature,locations,job_id:job,artifact_sha256:artifact,
      registration_sha256:row.registration_sha256||null,conflict:previous?.conflict===true
      ||Boolean(previous&&previous.signature!==signature)});
  }
  function related(family,parent,cell,anchor){
    if(family?.status==='verified')(family.rows||[]).forEach((row,i)=>record(row,parent,cell,`${anchor}-${i}`));
  }
  for(const [cell,base] of snapshot.rows.entries()){
    if(base.status!=='verified')continue;
    related(base.related,base.job_id,cell,`cell-${cell}-related`);
    for(const name of ['alternatives','policy_variants']){
      const family=base[name];
      if(family?.status!=='verified')continue;
      for(const [i,row] of (family.rows||[]).entries()){
        const anchor=`cell-${cell}-${name}-${i}`;
        record(row,base.job_id,cell,anchor);
        if(row.status==='verified')related(row.related,row.job_id,cell,`${anchor}-related`);
      }
    }
  }
  return [...candidates.values()];
}
export function independentAcceptance(snapshot){
  const rows=independentRecords(snapshot);
  return {accepted:rows.filter(r=>r.valid&&!r.conflict).length,
    conflicting:rows.filter(r=>r.conflict).length};
}
export function independentAcceptedEntries(snapshot){
  return independentRecords(snapshot).filter(r=>r.valid&&!r.conflict).flatMap(r=>
    r.locations.map(location=>({...location,job_id:r.job_id,artifact_sha256:r.artifact_sha256,
      registration_sha256:r.registration_sha256})));
}
