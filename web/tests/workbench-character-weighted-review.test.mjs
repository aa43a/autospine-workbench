import test from 'node:test';
import assert from 'node:assert/strict';
import {createWeightedReview} from '../modules/workbench-character-weighted-review.js';
import {needsBindingReview} from '../modules/workbench-character-ledger.js';
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const all=n=>[n,...n.children.flatMap(all)];
const document={createElement(tag){return {tag,children:[],append(...n){this.children.push(...n);},replaceChildren(...n){this.children=n;},setAttribute(){}};}};
const job={project_id:'p',job_id:'j',artifact_sha256:'a',layers:[{layer_id:'arm',name:'手臂',state:'weighted_candidate',regions:[{region_id:'part',state:'weighted_candidate'}],binding_decision:{decision_source:'pending'}}]};
const response={project_id:'p',job_id:'j',artifact_sha256:'a',authority:'none',can_review:true,eligible_layer_ids:['arm'],review_sha256:null,review:null};

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
