import assert from 'node:assert/strict';
import {test} from 'node:test';
import {transversePreflight,transverseSummary} from '../modules/motion-transverse-repair.js';

// Component state only: no claim about a browser, rendered layout, or GPU.
class Node {
  constructor(){this.children=[];this.textContent='';}
  append(...items){this.children.push(...items);}
  setAttribute(){}
}
globalThis.document={createElement:()=>new Node()};
const job={job_id:'motion-test',result:{artifact_sha256:'candidate'}},row={slot:'leg',animation:'motion'};
const valid={artifact_sha256:'candidate',...row,available:true,scope:{vertex_count:83}};

test('preflight reads exact candidate and explains experimental leg-only scope',async()=>{
  const calls=[];globalThis.fetch=async(...args)=>{calls.push(args);return {ok:true,json:async()=>valid};};
  const parent=new Node(),ui=transversePreflight(parent,job,row);
  await ui.show(true);assert.equal(ui.ready(),true);
  assert.equal(calls[0][0],'/api/motions/motion-test/view/transverse-repair/leg/motion.json');
  assert.equal(calls[0][1].method,undefined);
  assert.match(parent.children[0].textContent,/83 个顶点/);
  assert.match(parent.children[0].textContent,/预检不保证修复成功/);
});

test('hidden and superseded reads cannot authorize a stale save',async()=>{
  let finish;globalThis.fetch=()=>new Promise(resolve=>finish=resolve);
  const parent=new Node(),ui=transversePreflight(parent,job,row),pending=ui.show(true);
  await ui.show(false);finish({ok:true,json:async()=>valid});await pending;
  assert.equal(ui.ready(),false);assert.equal(parent.children[0].hidden,true);
  globalThis.fetch=async()=>({ok:true,json:async()=>({...valid,artifact_sha256:'other'})});
  await ui.show(true);assert.equal(ui.ready(),false);assert.match(parent.children[0].textContent,/候选或部件已变化/);
  globalThis.fetch=async()=>({ok:true,json:async()=>({...valid,available:false,reason_code:'motion_transverse_leg_required'})});
  await ui.show(true);assert.equal(ui.ready(),false);assert.match(parent.children[0].textContent,/只验证过腿部/);
});

test('summary keeps fixed-area failure, regressions and whole-character failures visible',()=>{
  const report={sample_count:129,maximum_displacement_px:13.4,geometry_passed:false,whole_character_passed:false,
    metrics:{failing_frame_count:{before:80,after:91}},regressions:['failing_frame_count','min_area_ratio'],
    fixed_area_blocker:{triangles:4,observations:27}};
  const text=transverseSummary(report).join(' ');
  assert.match(text,/129 个相同时刻/);assert.match(text,/80 → 91/);
  assert.match(text,/存在指标回退：失败帧数、最小面积比/);
  assert.match(text,/4 个三角形、27 条超限记录/);assert.match(text,/诊断候选/);
  const pass=transverseSummary({...report,geometry_passed:true,regressions:[],fixed_area_blocker:null}).join(' ');
  assert.match(pass,/当前部件：限定几何采样通过；整角色：仍有几何超限/);
  assert.match(pass,/播放与视觉需要独立验收/);
});
