import test from 'node:test';
import assert from 'node:assert/strict';
import {createFinalRegionReview} from '../modules/workbench-final-regions.js';

const document={createElement(tag){return {tag,children:[],append(...nodes){this.children.push(...nodes);},replaceChildren(...nodes){this.children=nodes;}};}};
const all=node=>[node,...node.children.flatMap(all)];
const job={job_id:'job-a',artifact_sha256:'a'.repeat(64),layers:[{layer_id:'layer',regions:[
  {region_id:'layer-residual',state:'static_reference'},
  {region_id:'layer-weighted-residual',state:'weighted_candidate'},
  {region_id:'layer-wing',state:'static_reference'}]}]};

test('explicit residual selection preserves exact scope and resets on a new candidate',()=>{
  const calls=[],view=createFinalRegionReview(document,value=>calls.push(value));
  view.sync(job,null,false);
  const check=all(view.element).find(n=>n.tag==='input');
  assert.equal(all(view.element).filter(n=>n.tag==='input').length,1);
  const save=all(view.element).find(n=>n.tag==='button');assert.equal(save.disabled,true);
  check.checked=true;check.onchange();save.onclick();
  assert.deepEqual(calls,[{action:'replace',job_id:job.job_id,expected_artifact_sha256:job.artifact_sha256,
    regions:[{layer_id:'layer',region_id:'layer-residual'}]}]);
  view.sync({...job,artifact_sha256:'b'.repeat(64)},null,false);
  assert.equal(all(view.element).find(n=>n.tag==='input').checked,false);
  assert.equal(all(view.element).find(n=>n.tag==='button').disabled,true);
});

test('saved history remains visible without a current candidate and can be revoked',()=>{
  const calls=[],view=createFinalRegionReview(document,value=>calls.push(value));
  view.sync(null,null,false);assert.equal(view.element.hidden,true);
  view.sync(null,{active:true,review:{decisions:[{}]}},true);
  assert.equal(view.element.hidden,false);assert.equal(all(view.element).find(n=>n.tag==='button').disabled,true);
  view.sync(null,{active:true,review:{decisions:[{}]}},false);
  all(view.element).find(n=>n.tag==='button').onclick();assert.deepEqual(calls,[{action:'revoke'}]);
});

test('post-component review is separate and only offered after a mount',()=>{
  const calls=[],view=createFinalRegionReview(document,value=>calls.push(value),{afterComponents:true});
  view.sync(job,null,false);assert.equal(view.element.hidden,true);
  view.sync({...job,component_mounts:{parent_review_required:false}},null,false);
  assert.equal(view.element.hidden,false);
  assert.match(view.element.children[0].textContent,/拆分后/);
  const check=all(view.element).find(n=>n.tag==='input');check.checked=true;check.onchange();
  all(view.element).find(n=>n.tag==='button').onclick();
  assert.equal(calls[0].expected_artifact_sha256,job.artifact_sha256);
});
