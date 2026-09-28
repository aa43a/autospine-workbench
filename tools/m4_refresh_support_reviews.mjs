// Append-only refresh of review decisions on unchanged snapshot evidence.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {join} from 'node:path';
import {supportReportHTML} from '../web/modules/motion-support-report.js';
import {supportExceptions} from '../web/modules/motion-support-exceptions.js';
import {matchingReviewRows,applyReviewRefresh} from './m4_review_refresh_helpers.mjs';
const [input,output,...jobs]=process.argv.slice(2);
if(!input||!output||!jobs.length||jobs.some(j=>!/^motion-[a-f0-9]{32}(?:@[a-f0-9]{64})?$/.test(j)))throw Error('Usage: INPUT_JSON NEW_OUTPUT_DIR JOB[@REGISTRATION]...');
const raw=await readFile(input),snapshot=JSON.parse(raw),origin='http://127.0.0.1:8918';
const updates=[];
for(const address of new Set(jobs)){
  const [job,registration=null]=address.split('@');
  const matches=matchingReviewRows(snapshot,job,registration);
  if(!matches.length)throw Error('candidate_not_in_verified_snapshot:'+job);
  const path=registration?`/related-candidates/${registration}/stage-review`:'/stage-review';
  const response=await fetch(`${origin}/api/motions/${job}${path}`,{signal:AbortSignal.timeout(180000)});
  if(!response.ok)throw Error('review_read_failed:'+job);
  const review=await response.json(),time=new Date().toISOString();
  applyReviewRefresh(matches,review,job,registration,time);
  updates.push({job_id:job,registration_sha256:registration,revision:review.revision,checked_at:time});
}
snapshot.review_refresh={parent_sha256:createHash('sha256').update(raw).digest('hex'),updates,
  scope:'review_only_same_evidence_original_source_and_inventory_read_times_retained'};
snapshot.exception_index=supportExceptions(snapshot);
await mkdir(output);
await writeFile(join(output,'report.json'),JSON.stringify(snapshot,null,2)+'\n',{flag:'wx'});
await writeFile(join(output,'index.html'),supportReportHTML(snapshot,origin),{flag:'wx'});
console.log(JSON.stringify(snapshot.review_refresh));
