import assert from 'node:assert/strict';
import {test} from 'node:test';
import {viewRows,appendViewTradeoffs} from '../modules/motion-view-tradeoffs.js';
function fixture(){
  return {profile:'candidate-source-view-tradeoffs-v1',artifact_sha256:'candidate',authority:'none',selected:false,production_authorized:false,
    current_yaw:0,source_samples:2,times:[0,.5],source_times:[2,2.5],candidates:Array.from({length:13},(_,i)=>({
      yaw_degrees:-90+15*i,current:i===6,
      knees:{sample_count:4,unmeasured_samples:0,samples_losing_30_degrees:1,minimum_length_ratio:.2,maximum_hidden_bend_deg:40,
        worst:{frame:1,side:'left',time:.5,source_time:2.5}},torso:{status:'measured',source_supported:i===6,reasons:[]},
      records:['arm','leg'].flatMap(limb=>['upper','lower'].flatMap(part=>['left','right'].map(side=>({
        role:`humanoid.${limb}.${part}.${side}`,collapsed_samples:limb==='arm'?1:0,minimum_visibility:.2}))))}))};
}
test('all views retain their competing measurements without adopting a camera',()=>{
  const f=fixture(),before=JSON.stringify(f),rows=viewRows(f,'candidate');
  assert.equal(rows.length,13);assert.equal(rows[0].armCollapsed,4);
  assert.equal(rows[0].torso.source_supported,false);assert.equal(rows[6].current,true);
  assert.equal(JSON.stringify(f),before);
});
test('wrong identities, unsupported scope, partial grids and invented seek times rejected',()=>{
  for(const change of [f=>f.artifact_sha256='other',f=>f.selected=true,f=>f.candidates.pop(),
    f=>f.candidates[0].knees.worst.time=2.5,f=>f.candidates[0].knees.sample_count=2,
    f=>f.candidates[0].records.pop(),f=>f.candidates[0].torso.source_supported=null,
    f=>f.times[1]=0,f=>f.candidates[0].knees.minimum_length_ratio=NaN]){
    const f=fixture();change(f);assert.throws(()=>viewRows(f,'candidate'));
  }
});
test('unmeasured torso stays explicit and missing knee observations have no seek target',()=>{
  const f=fixture(),r=f.candidates[0];r.torso={status:'unmeasured',source_supported:null,reasons:['degenerate']};
  r.knees.worst=null;r.knees.maximum_hidden_bend_deg=null;r.knees.unmeasured_samples=4;r.knees.samples_losing_30_degrees=0;
  const rows=viewRows(f,'candidate');assert.equal(rows[0].knees.worst,null);assert.equal(rows[0].torso.source_supported,null);
});
class Node{
  constructor(tag,text=''){this.tag=tag;this.textContent=text;this.children=[];}
  append(...items){this.children.push(...items);}replaceChildren(...items){this.children=items;}setAttribute(){}
}
const all=n=>[n,...n.children.flatMap(all)];
test('UI seeks current clip time, only reads API, and exposes comparison limitations',async()=>{
  const oldDoc=globalThis.document,oldFetch=globalThis.fetch;
  try{
    globalThis.document={createElement:tag=>new Node(tag)};
    const calls=[];globalThis.fetch=async(path,options)=>{calls.push({path,options});return {ok:true,json:async()=>fixture()};};
    const root=new Node('main'),seeks=[];appendViewTradeoffs(root,'/candidate/','candidate',t=>seeks.push(t));
    await root.children[0].onclick();
    assert.equal(calls[0].path,'/candidate/view-tradeoffs.json');assert.equal(calls[0].options.method,undefined);
    all(root).find(n=>n.tag==='button'&&n.textContent==='0.500 秒').onclick();assert.deepEqual(seeks,[.5]);
    assert.ok(all(root).some(n=>n.textContent.includes('不是所列视角的新动画')));
    assert.equal(root.children[0].disabled,false);
  }finally{globalThis.document=oldDoc;globalThis.fetch=oldFetch;}
});
