import assert from 'node:assert/strict';
import {test} from 'node:test';
import {garmentPreflight,garmentSummary} from '../modules/motion-garment-follow.js';

// Component logic only; no browser, no GPU or rendered-layout claim.
class Node {
  constructor(){this.children=[];this.textContent='';}
  append(...items){this.children.push(...items);}
  setAttribute(){}
}
globalThis.document={createElement:()=>new Node()};
const job={job_id:'motion-test',result:{artifact_sha256:'candidate'}},row={slot:'skirt',animation:'motion'};
const valid={artifact_sha256:'candidate',...row,available:true,scope:{roots:['left','right']}};

test('capability performs only an identity-bound read and explains scope',async()=>{
  const calls=[];globalThis.fetch=async(...args)=>{calls.push(args);return {ok:true,json:async()=>valid};};
  const parent=new Node(),ui=garmentPreflight(parent,job,row);
  await ui.show(true);assert.equal(ui.ready(),true);
  assert.equal(calls[0][0],'/api/motions/motion-test/view/garment-follow/skirt/motion.json');
  assert.equal(calls[0][1].method,undefined);
  assert.match(parent.children[0].textContent,/2 条已声明骨链/);
  assert.match(parent.children[0].textContent,/整段动作/);
});

test('hidden or superseded requests cannot authorize a later save',async()=>{
  let finish;globalThis.fetch=()=>new Promise(resolve=>finish=resolve);
  const parent=new Node(),ui=garmentPreflight(parent,job,row),pending=ui.show(true);
  await ui.show(false);finish({ok:true,json:async()=>valid});await pending;
  assert.equal(ui.ready(),false);assert.equal(parent.children[0].hidden,true);
  globalThis.fetch=async()=>({ok:true,json:async()=>({...valid,artifact_sha256:'other'})});
  await ui.show(true);assert.equal(ui.ready(),false);assert.match(parent.children[0].textContent,/候选或部件已变化/);
  globalThis.fetch=async()=>({ok:true,json:async()=>({...valid,available:false,reason_code:'motion_garment_torso_required'})});
  await ui.show(true);assert.equal(ui.ready(),false);assert.match(parent.children[0].textContent,/没有躯干投影数据/);
});

test('summary separates contact measurements from visual acceptance and missing data',()=>{
  const report={roots:['chain'],maximum_root_shift_px:13.56,validation_sample_count:3713,
    waist_contact:{status:'measured',anchors:17,before:{separation_px:.02},after:{separation_px:.01}}};
  assert.match(garmentSummary(report).join(' '),/3713 个相同时刻/);
  assert.match(garmentSummary(report).join(' '),/0.0200 → 0.0100/);
  assert.match(garmentSummary({...report,waist_contact:{status:'unavailable'}}).join(' '),/不能将其视为通过/);
});
