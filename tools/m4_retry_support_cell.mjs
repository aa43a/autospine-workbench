// Re-read one incomplete cell; preserve the original snapshot and all other cells.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {join} from 'node:path';
import {collectSupportSnapshot,validatePack} from '../web/modules/motion-support-snapshot.js';
import {supportReportHTML,supportTotals} from '../web/modules/motion-support-report.js';
import {supportExceptions} from '../web/modules/motion-support-exceptions.js';
const [input,packPath,job,output]=process.argv.slice(2);
if(!input||!packPath||!output||!/^motion-[a-f0-9]{32}$/.test(job))throw Error('Usage: INPUT PACK JOB NEW_OUTPUT');
const raw=await readFile(input),snapshot=JSON.parse(raw),pack=validatePack(JSON.parse(await readFile(packPath,'utf8')));
if(snapshot.plan_sha256!==pack.plan_sha256)throw Error('plan_changed');
const index=snapshot.rows.findIndex(r=>r.job_id===job),old=snapshot.rows[index];
if(!old||snapshot.rows.filter(r=>r.job_id===job).length!==1)throw Error('ambiguous_cell');
if(old.status==='verified'&&['related','alternatives','policy_variants'].every(k=>old[k]?.complete))throw Error('cell_already_complete');
const group=pack.groups.find(g=>g.targets.some(t=>t.job_id===job));
const target=group?.targets.find(t=>t.job_id===job);
if(!target||target.artifact_sha256!==old.artifact_sha256||group.job_id!==old.source_job_id
  ||group.source_sha256!==old.source_sha256||group.label!==old.motion||target.label!==old.character)throw Error('cell_identity_changed');
await mkdir(output);
const origin='http://127.0.0.1:8918';
const delta=await collectSupportSnapshot({...pack,groups:[{...group,targets:[target]}],
  coverage:{expected:1,available:1,missing:[]}},async path=>{
  const response=await fetch(origin+path,{signal:AbortSignal.timeout(600000)});
  const value=await response.json();if(!response.ok)throw Error(value.reason_code||`HTTP ${response.status}`);
  return value;
},{onProgress:p=>console.log(`${p.finished}/${p.total} ${p.phase}`)});
const replacement=delta.rows[0];
if(replacement.status!=='verified'||replacement.review.revision<(old.review?.revision||0))throw Error('cell_recheck_failed');
const merged=structuredClone(snapshot);merged.rows[index]=replacement;
merged.cell_refresh={parent_sha256:createHash('sha256').update(raw).digest('hex'),
  job_id:job,started_at:delta.started_at,finished_at:delta.finished_at,
  original_finished_at:snapshot.finished_at,scope:'one_cell_reread_other_cells_keep_original_timestamps'};
merged.finished_at=delta.finished_at;merged.exception_index=supportExceptions(merged);
await writeFile(join(output,'cell.json'),JSON.stringify(delta,null,2)+'\n',{flag:'wx'});
await writeFile(join(output,'report.json'),JSON.stringify(merged,null,2)+'\n',{flag:'wx'});
await writeFile(join(output,'index.html'),supportReportHTML(merged,origin),{flag:'wx'});
console.log(JSON.stringify(supportTotals(merged)));
