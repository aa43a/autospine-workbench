import assert from 'node:assert/strict';
import {test} from 'node:test';
import {appendPoseChecks} from '../modules/motion-related-pose.js';
import {appendRelatedCandidates} from '../modules/motion-related-candidates.js';

// Plain component logic; does not operate a browser or verify rendering.
class Node {
  constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.style={};}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;this.textContent='';}
  setAttribute(){}
}
globalThis.document={createElement:tag=>new Node(tag),createTextNode:text=>text};
globalThis.window={addEventListener(){},removeEventListener(){}};
const walk=n=>[n,...n.children.flatMap(c=>c instanceof Node?walk(c):[])];
const find=(n,text)=>walk(n).find(x=>x.textContent===text);
const checks={samples:57,yaw_degrees:-55,
  limbs:[{limb:'leg',side:'right',max_direction_error_degrees:3.66,max_endpoint_error_ratio:.037,
    worst_time:.266667,source_time:1.266667}],
  events:[{side:'right',reason:'target_bend_flattened',time:1.733333,source_time:2.733333}]};

test('exact player times survive rounded labels and source clip offsets',()=>{
  const root=new Node('main'),times=[];appendPoseChecks(root,checks,t=>times.push(t));
  const buttons=walk(root).filter(n=>n.tag==='button');buttons.forEach(b=>b.onclick());
  assert.deepEqual(times,[.266667,1.733333]);
  assert.ok(walk(root).some(n=>n.textContent.includes('源 2.733 秒')));
  assert.ok(walk(root).some(n=>n.textContent.includes('未检查帧间插值')));
});

test('pose locator stays in exact related registration and never posts a review',async()=>{
  const artifact='a'.repeat(64),registration='b'.repeat(64),baseline='c'.repeat(64),calls=[];
  globalThis.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>({
    baseline_sha256:baseline,rows:[{registration_sha256:registration,candidate_sha256:artifact,
      runtime_version:'4.3.13',sampled_frames:3713,pose_checks:checks}]})};};
  const root=new Node('main');appendRelatedCandidates(root,{job_id:'motion-test',result:{artifact_sha256:baseline}});
  await find(root,'查看已关联改进候选').onclick();
  walk(root).filter(n=>n.textContent==='定位此姿态').at(-1).onclick();
  const frame=walk(root).find(n=>n.tag==='iframe');
  assert.equal(frame.src,`/api/motions/motion-test/view/related-candidates/${registration}/player.html?time=1.733333`);
  assert.equal(calls.length,1);assert.equal(calls[0].options.method,undefined);
});

test('depth conflict opens the registered candidate at its exact time',async()=>{
  const artifact='a'.repeat(64),registration='b'.repeat(64),baseline='c'.repeat(64),calls=[];
  globalThis.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>({
    baseline_sha256:baseline,rows:[{registration_sha256:registration,candidate_sha256:artifact,
      runtime_version:'4.3.13',sampled_frames:969,depth_diagnostics:{failures:[
        {time:.033333,pair:['arm','torso'],reason_code:'visible_depth_straddle'}]}}]})};};
  const root=new Node('main');appendRelatedCandidates(root,{job_id:'motion-test',result:{artifact_sha256:baseline}});
  await find(root,'查看已关联改进候选').onclick();
  find(root,'查看此时刻').onclick();
  assert.equal(walk(root).find(n=>n.tag==='iframe').src,
    `/api/motions/motion-test/view/related-candidates/${registration}/player.html?time=0.033333`);
  assert.equal(calls.length,1);assert.equal(calls[0].options.method,undefined);
});
