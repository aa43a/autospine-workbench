import test from 'node:test';
import assert from 'node:assert/strict';
import {createWeightedReview} from '../modules/workbench-character-weighted-review.js';
import {needsBindingReview} from '../modules/workbench-character-ledger.js';
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const all=n=>[n,...n.children.flatMap(all)];
const document={createElement(tag){return {tag,children:[],append(...n){this.children.push(...n);},replaceChildren(...n){this.children=n;},setAttribute(){}};}};
const job={project_id:'p',job_id:'j',artifact_sha256:'a',layers:[{layer_id:'arm',name:'手臂',state:'weighted_candidate',regions:[{region_id:'part',state:'weighted_candidate'}],binding_decision:{decision_source:'pending',action:'pending'}}]};
const response={project_id:'p',job_id:'j',artifact_sha256:'a',authority:'none',can_review:true,eligible_layer_ids:['arm'],review_sha256:null,review:null};

test('system defaults show provenance and allow stage exceptions',async()=>{
 const view=createWeightedReview(document,{apiRequest:async(_url,init)=>({...response,
  default_review:{accepted_layer_ids:['arm']},confirmed_layer_ids:init.method==='POST'?[]:['arm']})});
 view.sync(job,true);await flush();
 assert.ok(all(view.element).some(n=>n.textContent.includes('系统默认采用，可撤销')));
 assert.deepEqual(view.confirmed(),['arm']);
 all(view.element).find(n=>n.textContent==='撤销区域确认').onclick();await flush();
 assert.deepEqual(view.confirmed(),[]);view.dispose();
});

test('inherited binding is visible, source-bound and independently revocable',async()=>{
 let body;const view=createWeightedReview(document,{apiRequest:async(_url,init)=>{
   if(init.method==='POST'){body=JSON.parse(init.body);return {...response,confirmed_layer_ids:[],review:{accepted_layer_ids:[],revoked_replayed_layer_ids:['arm']}};}
   return {...response,confirmed_layer_ids:['arm'],replay_sha256:'proof',replayed_review:{accepted_layer_ids:['arm']}};
 }});
 view.sync(job,true);await flush();assert.deepEqual(view.confirmed(),['arm']);
 assert.ok(all(view.element).some(n=>n.textContent.includes('沿用未变化区域的原确认')));
 all(view.element).find(n=>n.textContent==='撤销区域确认').onclick();await flush();
 assert.equal(body.expected_replay_sha256,'proof');assert.equal(body.action,'revoke');
 assert.deepEqual(view.confirmed(),[]);view.dispose();
});

test('loads once, sends exact confirmation, and supports revocation without rebinding',async()=>{
 const calls=[];let saved=false;
 const view=createWeightedReview(document,{apiRequest:async(url,init)=>{calls.push([url,init]);if(init.method==='POST')saved=JSON.parse(init.body).action==='confirm';return {...response,review_sha256:'r',review:{accepted_layer_ids:saved?['arm']:[]}};}});
 view.sync(job,true);await flush();view.sync(job,true);assert.equal(calls.length,1);
 all(view.element).find(n=>n.textContent==='确认这些区域的绑定').onclick();await flush();
 assert.deepEqual(JSON.parse(calls[1][1].body),{expected_artifact_sha256:'a',expected_review_sha256:'r',layer_id:'arm',action:'confirm'});
 assert.deepEqual(view.confirmed(),['arm']);assert.equal(needsBindingReview(job.layers[0],view.confirmed()),false);
 all(view.element).find(n=>n.textContent==='撤销区域确认').onclick();await flush();assert.deepEqual(view.confirmed(),[]);
 assert.equal(needsBindingReview(job.layers[0],view.confirmed()),true);view.dispose();
});

test('dirty state waits; late response and wrong candidate cannot restore confirmation',async()=>{
 let release;const view=createWeightedReview(document,{apiRequest:()=>new Promise(resolve=>{release=resolve;})});
 view.sync(job,false);assert.equal(release,undefined);view.sync(job,true);
 view.sync(null,false);release({...response,review:{accepted_layer_ids:['arm']}});await flush();assert.deepEqual(view.confirmed(),[]);
 const bad=createWeightedReview(document,{apiRequest:async()=>({...response,artifact_sha256:'other',review:{accepted_layer_ids:['arm']}})});
 bad.sync(job,true);await flush();assert.deepEqual(bad.confirmed(),[]);view.dispose();bad.dispose();
});

test('partial regions cannot disappear from the exception list',()=>{
 assert.equal(needsBindingReview({...job.layers[0],state:'partial'},['arm']),true);
 assert.equal(needsBindingReview({...job.layers[0],binding_decision:{decision_source:'policy_auto',evidence_current:false}},['arm']),true);
});

test('batch defaults empty, submits selected IDs once, and clears across candidates',async()=>{
 const posts=[];let selected=[];
 const value={...job,layers:[...job.layers,{...job.layers[0],layer_id:'leg',name:'腿'}]};
 const view=createWeightedReview(document,{apiRequest:async(_url,init)=>{
  if(init.method==='POST'){const body=JSON.parse(init.body);posts.push(body);selected=body.layer_ids;}
  return {...response,eligible_layer_ids:['arm','leg'],review:{accepted_layer_ids:selected}};
 }});
 view.sync(value,true);await flush();
 const button=()=>all(view.element).find(n=>n.tag==='button'&&n.textContent.startsWith('确认勾选区域'));
 assert.equal(button().disabled,true);
 let boxes=all(view.element).filter(n=>n.type==='checkbox');assert.ok(boxes.every(n=>!n.checked));
 boxes[0].checked=true;boxes[0].onchange();boxes=all(view.element).filter(n=>n.type==='checkbox');
 boxes[1].checked=true;boxes[1].onchange();button().onclick();await flush();
 assert.equal(posts.length,1);assert.deepEqual(posts[0].layer_ids,['arm','leg']);assert.equal(posts[0].layer_id,undefined);
 assert.deepEqual(view.confirmed(),['arm','leg']);assert.equal(button().disabled,true);
 boxes=all(view.element).filter(n=>n.type==='checkbox');boxes[0].checked=true;boxes[0].onchange();
 view.sync(value,false);assert.equal(button().disabled,true);
 view.sync(null,false);assert.equal(button().disabled,true);view.dispose();
});

test('select pending excludes accepted layers and does not submit a decision',async()=>{
 const calls=[];const value={...job,layers:[...job.layers,{...job.layers[0],layer_id:'leg',name:'腿'}]};
 const view=createWeightedReview(document,{apiRequest:async(_url,init)=>{calls.push(init);return {...response,eligible_layer_ids:['arm','leg'],review:{accepted_layer_ids:['arm']}};}});
 view.sync(value,true);await flush();
 all(view.element).find(n=>n.textContent==='勾选待确认').onclick();
 assert.deepEqual(all(view.element).filter(n=>n.type==='checkbox').map(n=>n.checked),[false,true]);
 assert.equal(calls.length,1);view.dispose();
});
