import assert from 'node:assert/strict';
import {test} from 'node:test';
import {appendDepthTimeline} from '../modules/motion-depth-timeline.js';
class Node {
  constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.attrs={};}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;this.textContent='';}
  setAttribute(name,value){this.attrs[name]=value;}
}
globalThis.document={createElement:tag=>new Node(tag)};
const descendants=node=>[node,...node.children.flatMap(n=>n instanceof Node?descendants(n):[])];
const report=()=>({profile:'external-motion-depth-navigation-v1',artifact_sha256:'asset',
  skeleton_sha256:'skeleton',authority:'none',order_changed:false,original_order_records:1,
  diagnostic_records:1,navigable_samples:2,groups:[{pair:['arm','body'],reason:'visible_depth_straddle',
    time_source:'overlap_sample',samples:[{time:.125,order_times:[0]},{time:.375,order_times:[.25]}]}]});
const job={job_id:'test',result:{artifact_sha256:'asset'}};

test('seeks actual midpoint and isolates exact pair without mutating any review',async()=>{
  const requests=[];globalThis.fetch=async(url,options)=>{requests.push([url,options]);return{ok:true,json:async()=>report()};};
  const root=new Node('main');let time=null,pair=null;
  appendDepthTimeline(root,job,{skeleton_sha256:'skeleton'},t=>time=t,p=>pair=p);
  await root.children[0].onclick();const nodes=descendants(root);
  assert.equal(requests[0][0],'/api/motions/test/view/depth-navigation.json');
  assert.equal(requests[0][1].method,undefined);
  assert.ok(nodes.some(n=>n.textContent.includes('不证明画面已发生穿插')));
  assert.ok(nodes.some(n=>n.textContent.includes('原判定起点 0.000000')));
  const slider=nodes.find(n=>n.tag==='input');slider.value='1';slider.oninput();
  nodes.find(n=>n.tag==='a').onclick({preventDefault(){}});assert.equal(time,.375);
  nodes.find(n=>n.textContent==='同页隔离相关部件').onclick();
  assert.equal(time,.375);assert.deepEqual(pair,['arm','body']);assert.equal(requests.length,1);
});

test('stale candidate or skeleton cannot offer a seek action',async()=>{
  for(const change of [{artifact_sha256:'other'},{skeleton_sha256:'other'}]){
    globalThis.fetch=async()=>({ok:true,json:async()=>({...report(),...change})});
    const root=new Node('main');appendDepthTimeline(root,job,{skeleton_sha256:'skeleton'});
    await root.children[0].onclick();assert.match(root.children[1].textContent,/证据已变化/);
    assert.equal(descendants(root).filter(n=>n.tag==='a').length,0);
  }
});

test('unmeasured records have an explicit explanation and independent fallback link',async()=>{
  const value=report();value.groups[0].reason='depth_overlap_pixel_budget';
  value.groups[0].time_source='unmeasured_sample';
  globalThis.fetch=async()=>({ok:true,json:async()=>value});
  const root=new Node('main');appendDepthTimeline(root,job,{skeleton_sha256:'skeleton'});
  await root.children[0].onclick();const nodes=descendants(root);
  assert.ok(nodes.some(n=>n.textContent.includes('不计作已看到的画面错误')));
  assert.equal(nodes.find(n=>n.tag==='a').href,'/api/motions/test/view/player.html?time=0.125');
});
