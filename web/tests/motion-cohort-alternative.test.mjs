import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createAlternativePanel} from '../modules/motion-cohort-alternative.js';
class Node {
  constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.style={};}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;this.textContent='';}
  setAttribute(){}
  scrollIntoView(){}
}
globalThis.document={createElement:tag=>new Node(tag),createTextNode:text=>text};
globalThis.window={addEventListener(){},removeEventListener(){}};
const walk=n=>[n,...n.children.flatMap(c=>c instanceof Node?walk(c):[])];
test('alternative exposes its own related candidate, and closing cancels stale loads',async()=>{
  const jobId='motion-'+'a'.repeat(32),sourceId='motion-'+'b'.repeat(32),artifact='c'.repeat(64);
  const row={job_id:jobId,source_job_id:sourceId,artifact_sha256:artifact,evidence_sha256:'e'.repeat(64),view:'side'};
  const motion={motion_ir_sha256:'f'.repeat(64)};
  const job={job_id:jobId,kind:'adapt',status:'succeeded',result:{artifact_sha256:artifact}};
  const source={job_id:sourceId,status:'succeeded',source_sha256:'source',result:{motion,fps:30,frame_count:31,duration_seconds:1}};
  const link={authority:'none',target_job_id:jobId,artifact_sha256:artifact,source_job_id:sourceId,source_sha256:'source',
    motion_identity:motion,source_fps:30,source_frame_count:31,source_duration:1,source_start:0,source_end:1,duration:1,clip:null};
  const request=async path=>path.endsWith('stage-review')?{artifact_sha256:artifact,evidence_sha256:row.evidence_sha256}:
    path.endsWith('source-link.json')?link:path.endsWith(sourceId)?source:job;
  const root=new Node('main'),panel=createAlternativePanel(root,request);
  await panel.open(row,'source');
  const button=walk(root).find(n=>n.textContent==='查看已关联改进候选');assert.ok(button);
  let response,signal,calls=0;
  globalThis.fetch=(url,options)=>{calls++;assert.equal(url,`/api/motions/${jobId}/view/related-candidates.json`);
    signal=options.signal;return new Promise(resolve=>{response=resolve;});};
  const loading=button.onclick();panel.clear();assert.equal(signal.aborted,true);
  response({ok:true,json:async()=>({baseline_sha256:artifact,rows:[]})});await loading;
  assert.equal(root.children.length,0);assert.equal(calls,1);
});
