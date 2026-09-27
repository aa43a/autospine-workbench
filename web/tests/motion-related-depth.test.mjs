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
