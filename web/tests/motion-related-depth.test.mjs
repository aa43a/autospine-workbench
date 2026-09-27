import assert from 'node:assert/strict';
import {test} from 'node:test';
import {appendDepthDiagnostics} from '../modules/motion-related-depth.js';
class Node {
  constructor(tag){this.tag=tag;this.children=[];this.textContent='';}
  append(...nodes){this.children.push(...nodes);}
}
globalThis.document={createElement:tag=>new Node(tag)};
const walk=n=>[n,...n.children.flatMap(walk)];
test('all conflicts remain locatable at exact candidate times without saving reviews',()=>{
  const root=new Node('main'),seen=[];
  const checks={failures:[0,.033333,4.033333].map(time=>({time,pair:['arm','torso'],reason_code:'visible_depth_straddle'}))};
  appendDepthDiagnostics(root,checks,time=>seen.push(time));
  walk(root).filter(n=>n.tag==='button').forEach(n=>n.onclick());
  assert.deepEqual(seen,[0,.033333,4.033333]);
  assert.ok(walk(root).some(n=>n.textContent.includes('阶段接受不清除')));
});
test('missing evidence adds no claim; empty conflicts still require review',()=>{
  const root=new Node('main');appendDepthDiagnostics(root,null,()=>{});
  assert.equal(root.children.length,0);
  appendDepthDiagnostics(root,{failures:[]},()=>{});
  assert.ok(walk(root).some(n=>n.textContent.includes('完整遮挡检查仍需')));
});

test('missing samples remain separate from failures and budget limits are not called conflicts',()=>{
  const root=new Node('main');
  appendDepthDiagnostics(root,{coverage:{visible_pair_samples:134,ambiguous_visible_pair_samples:32,
    order_mismatch_pair_samples:69,unmeasured_pair_samples:110},
    failures:[{time:1,pair:['arm','torso'],reason_code:'depth_overlap_pixel_budget'}]},()=>{});
  const text=walk(root).map(n=>n.textContent).join('\n');
  assert.match(text,/1 条失败记录/);assert.match(text,/未测 110/);
  assert.match(text,/未测：像素检查预算不足/);assert.doesNotMatch(text,/1 条冲突/);
  const legacy=new Node('main');appendDepthDiagnostics(legacy,{failures:[]},()=>{});
  assert.match(walk(legacy).map(n=>n.textContent).join('\n'),/采样覆盖未记录/);
});
