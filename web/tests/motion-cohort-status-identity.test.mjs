import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createCohortStatus} from '../modules/motion-cohort-status.js';

// Component state and request flow only, not a browser/layout test.
class Node {
  constructor(tag){this.tag=tag;this.children=[];this.attrs={};this.style={};this.textContent='';this.value='';}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=items;this.textContent='';}
  setAttribute(k,v){this.attrs[k]=v;}
}
function all(root){return [root,...root.children.filter(n=>n instanceof Node).flatMap(all)];}
function text(root){return root.textContent+root.children.map(n=>n instanceof Node?text(n):n).join(' ');}
function fixture(){
  const root=new Node('main'),events={},calls=[];let bad=false;
  globalThis.document={createElement:tag=>new Node(tag)};
  globalThis.window={addEventListener:(name,fn)=>events[name]=fn};
  const source={job_id:'source',status:'succeeded',source_sha256:'bytes',result:{
    motion:{motion_ir_sha256:'ir'},fps:30,frame_count:121,duration_seconds:4}};
  globalThis.fetch=async path=>{
    calls.push(path);let value;
    if(path==='/api/motions/source')value=source;
    else if(path.endsWith('/source-link.json'))value={authority:'none',target_job_id:'target',
      artifact_sha256:'asset',source_job_id:bad?'unrelated':'source',source_sha256:'bytes',
      motion_identity:{motion_ir_sha256:'ir'},source_fps:30,source_frame_count:121,source_duration:4,
      source_start:0,source_end:4,duration:4,clip:null};
    else if(path.endsWith('/stage-review'))value={artifact_sha256:'asset',
      readiness:{artifact_sha256:'asset',status:'stage_review',stages:[]},
      current_applies:true,current:{decision:'accepted',notes:'已确认'}};
    else if(path.endsWith('/related-candidates.json'))value={baseline_sha256:'asset',authority:'none',rows:[]};
    else value={job_id:'target',kind:'adapt',status:'succeeded',result:{artifact_sha256:'asset',clip:null}};
    return {ok:true,json:async()=>value};
  };
  createCohortStatus(root,{groups:[{label:'move',job_id:'source',source_sha256:'bytes',
    targets:[{label:'character',job_id:'target',artifact_sha256:'asset'}]}]},()=>{});
  const refresh=all(root).find(n=>n.textContent==='核对全部候选状态');
  return {root,calls,events,refresh,bad:()=>bad=true};
}

test('mismatched source does not fetch acceptance or contribute to counts',async()=>{
  const f=fixture();f.bad();await f.refresh.onclick();
  assert.match(text(f.root),/候选与当前源动作不匹配/);
  assert.match(text(f.root),/已读取 0\/1.*有效阶段接受 0\/1/);
  assert.equal(f.calls.some(p=>p.endsWith('/stage-review')),false);
});

test('successful old summary is cleared when relationship verification later fails',async()=>{
  const f=fixture();await f.refresh.onclick();assert.match(text(f.root),/有效阶段接受 1\/1/);
  f.bad();await f.refresh.onclick();
  assert.match(text(f.root),/有效阶段接受 0\/1/);
  assert.doesNotMatch(text(f.root),/验收说明：已确认/);
  assert.equal(f.calls.filter(p=>p.endsWith('/stage-review')).length,1);
});

test('review-saved event prevents an in-flight source read from replacing newer state',async()=>{
  const f=fixture(),fetch=globalThis.fetch;let finish,entered;
  const waiting=new Promise(resolve=>entered=resolve);
  globalThis.fetch=async path=>{
    if(path.endsWith('/source-link.json')){entered();await new Promise(resolve=>finish=resolve);}
    return fetch(path);
  };
  const pending=f.refresh.onclick();await waiting;
  f.events['motion-stage-review-saved']({detail:{jobId:'target'}});finish();await pending;
  assert.match(text(f.root),/结论已更新，请重新核对/);
  assert.match(text(f.root),/有效阶段接受 0\/1/);
});
