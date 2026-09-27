// Append-only refresh of review decisions on unchanged snapshot evidence.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {join} from 'node:path';
import {supportReportHTML} from '../web/modules/motion-support-report.js';
import {supportExceptions} from '../web/modules/motion-support-exceptions.js';
const [input,output,...jobs]=process.argv.slice(2);
if(!input||!output||!jobs.length||jobs.some(j=>!/^motion-[a-f0-9]{32}$/.test(j)))throw Error('Usage: INPUT_JSON NEW_OUTPUT_DIR JOB...');
const raw=await readFile(input),snapshot=JSON.parse(raw),origin='http://127.0.0.1:8918';
const updates=[];
for(const job of new Set(jobs)){
  const matches=snapshot.rows.flatMap(r=>[r,...(r.alternatives?.rows||[]),...(r.policy_variants?.rows||[])])
    .filter(r=>r.job_id===job&&r.status==='verified');
  if(!matches.length)throw Error('candidate_not_in_verified_snapshot:'+job);
  const response=await fetch(`${origin}/api/motions/${job}/stage-review`,{signal:AbortSignal.timeout(180000)});
  if(!response.ok)throw Error('review_read_failed:'+job);
  const review=await response.json(),time=new Date().toISOString();
  for(const row of matches){
    if(review.job_id!==job||review.artifact_sha256!==row.artifact_sha256
      ||review.evidence_sha256!==row.review.evidence_sha256
      ||JSON.stringify(review.readiness)!==JSON.stringify(row.review.readiness)
      ||review.revision<row.review.revision||review.authority!=='none'||review.production_authorized!==false
      ||!review.current_applies||review.current?.artifact_sha256!==row.artifact_sha256
      ||review.current?.evidence_sha256!==review.evidence_sha256
      ||review.current?.revision!==review.revision)throw Error('review_evidence_changed:'+job);
    row.review=structuredClone(review);row.review_checked_at=time;
  }
  updates.push({job_id:job,revision:review.revision,checked_at:time});
}
snapshot.review_refresh={parent_sha256:createHash('sha256').update(raw).digest('hex'),updates,
  scope:'review_only_same_evidence_original_source_and_inventory_read_times_retained'};
snapshot.exception_index=supportExceptions(snapshot);
await mkdir(output);
await writeFile(join(output,'report.json'),JSON.stringify(snapshot,null,2)+'\n',{flag:'wx'});
await writeFile(join(output,'index.html'),supportReportHTML(snapshot,origin),{flag:'wx'});
console.log(JSON.stringify(snapshot.review_refresh));
