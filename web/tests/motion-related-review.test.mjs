import assert from 'node:assert/strict';
import {test} from 'node:test';
import {appendStageReview} from '../modules/motion-stage-review.js';
import {appendRelatedCandidates} from '../modules/motion-related-candidates.js';
import {relatedSummary} from '../modules/motion-related-summary.js';
import {createCohortStatus} from '../modules/motion-cohort-status.js';

// Component logic only: no browser process or browser permissions are involved.
class Node {
  constructor(tag){this.tag=tag;this.children=[];this.attrs={};this.textContent='';this.style={};this.value='';}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;this.textContent='';}
  setAttribute(key,value){this.attrs[key]=value;}
  add(option){this.children.push(option);}
  focus(){}
}
globalThis.document={createElement:tag=>new Node(tag),createTextNode:text=>text};
globalThis.Option=class extends Node {constructor(text,value){super('option');this.textContent=text;this.value=value;}};
const walk=node=>[node,...node.children.flatMap(n=>n instanceof Node?walk(n):[])];
const find=(root,label)=>walk(root).find(n=>n.textContent===label);
const artifact='a'.repeat(64),registration='b'.repeat(64),second='c'.repeat(64),baseline='d'.repeat(64);
const job={job_id:'motion-test',result:{artifact_sha256:artifact}};
const baseState=()=>({job_id:job.job_id,artifact_sha256:artifact,registration_sha256:registration,
  evidence_sha256:'e'.repeat(64),revision:0,current:null,current_applies:false,history:[],
  readiness:{artifact_sha256:artifact,registration_sha256:registration,status:'evidence_incomplete',
    stages:[{stage:'Runtime',status:'sampled_pass'},{stage:'遮挡',status:'unmeasured',explanation:'未验证完整动作'}]}});
function harness(state=baseState()){
  const calls=[],events=[];
  globalThis.window={dispatchEvent:e=>events.push(e),addEventListener(){},removeEventListener(){}};
  globalThis.CustomEvent=class{constructor(type,options){this.type=type;this.detail=options.detail;}};
  globalThis.fetch=async(url,options={})=>{
    calls.push({url,options});
    if(options.method==='POST'){
      const body=JSON.parse(options.body);
      state={...state,revision:state.revision+1,current_applies:true,
        current:{...body,revision:state.revision+1,created_at:'now',production_authorized:false}};
      state.history=[...state.history,state.current];
    }
    return {ok:true,json:async()=>structuredClone(state)};
  };
  return {calls,events};
}

test('related form saves exact registration, retains unknowns, then revokes without a baseline event',async()=>{
  const {calls,events}=harness(),root=new Node('main');
  appendStageReview(root,job,{registration});
  await find(root,'记录 / 查看阶段验收').onclick();
  assert.match(calls[0].url,new RegExp(`/related-candidates/${registration}/stage-review$`));
  const select=walk(root).find(n=>n.tag==='select');
  assert.equal(select.children.find(n=>n.value==='accepted').disabled,true);
  const save=find(root,'保存阶段结论'),notes=walk(root).find(n=>n.tag==='textarea');
  const checked=walk(root).find(n=>n.type==='checkbox');
  select.value='accepted_with_exceptions';select.onchange();
  checked.checked=true;checked.onchange();assert.equal(save.disabled,true);
  notes.value='仅接受当前片段；遮挡仍未验证';notes.oninput();assert.equal(save.disabled,false);
  await save.onclick();
  const body=JSON.parse(calls[1].options.body);
  assert.equal(body.registration_sha256,registration);assert.equal(body.artifact_sha256,artifact);
  assert.equal(body.expected_revision,0);assert.equal(calls[1].options.headers['X-Autospine-Intent'],'pipeline-preview');
  assert.match(root.children[0].textContent,/待处理或未验证：遮挡/);
  assert.equal(events[0].type,'motion-related-review-saved');assert.equal(events[0].detail.registration,registration);
  const next=walk(root).find(n=>n.tag==='select');next.value='revoked';next.onchange();
  const confirm=walk(root).find(n=>n.type==='checkbox');confirm.checked=true;confirm.onchange();
  await find(root,'保存阶段结论').onclick();
  assert.equal(JSON.parse(calls[2].options.body).expected_revision,1);
  assert.match(root.children[0].textContent,/已撤销/);
  assert.equal(events.some(e=>e.type==='motion-stage-review-saved'),false);
});

test('stale registration blocks the form even when candidate bytes are identical',async()=>{
  const state=baseState();state.registration_sha256=second;harness(state);
  const root=new Node('main');appendStageReview(root,job,{registration});
  await find(root,'记录 / 查看阶段验收').onclick();
  assert.match(root.children[0].textContent,/关联记录已变化/);
  assert.equal(walk(root).some(n=>n.tag==='select'),false);
});

test('baseline review still sends the original body and baseline event',async()=>{
  const {calls,events}=harness(),root=new Node('main');appendStageReview(root,job);
  await find(root,'记录 / 查看阶段验收').onclick();
  const select=walk(root).find(n=>n.tag==='select');select.value='rejected';select.onchange();
  const checked=walk(root).find(n=>n.type==='checkbox');checked.checked=true;checked.onchange();
  const notes=walk(root).find(n=>n.tag==='textarea');notes.value='手腕需调整';notes.oninput();
  await find(root,'保存阶段结论').onclick();
  assert.equal(calls[1].url,'/api/motions/motion-test/stage-review');
  assert.equal('registration_sha256' in JSON.parse(calls[1].options.body),false);
  assert.equal(events[0].type,'motion-stage-review-saved');
});

test('same-page player, review endpoint and download all address the selected registration',async()=>{
  const report={baseline_sha256:baseline,rows:[registration,second].map(reg=>({
    registration_sha256:reg,candidate_sha256:artifact,runtime_version:'4.3.13',sampled_frames:2}))};
  const {calls}=harness();
  globalThis.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>
    url.endsWith('related-candidates.json')?report:{...baseState(),registration_sha256:second,
      readiness:{...baseState().readiness,registration_sha256:second}}};};
  const root=new Node('main');appendRelatedCandidates(root,{...job,result:{artifact_sha256:baseline}});
  await find(root,'查看已关联改进候选').onclick();
  const details=walk(root).filter(n=>n.tag==='details'),chosen=details[1];
  find(chosen,'加载改进候选时间轴').onclick();
  assert.ok(walk(chosen).find(n=>n.tag==='iframe').src.includes(`/related-candidates/${second}/player.html`));
  await find(chosen,'记录 / 查看阶段验收').onclick();
  assert.ok(calls[1].url.includes(`/related-candidates/${second}/stage-review`));
  assert.ok(find(chosen,'下载此候选（含异常与来源记录）').href.includes(`/related-candidates/${second}/candidate.zip`));
  assert.equal(calls.some(c=>c.options?.method==='POST'),false);
});

test('new review supersedes imported acceptance in summary; revoke and stale stay explicit',()=>{
  const state=baseState();state.revision=1;state.current_applies=true;
  state.current={registration_sha256:registration,artifact_sha256:artifact,evidence_sha256:state.evidence_sha256,
    revision:1,decision:'revoked',production_authorized:false};
  const row={registration_sha256:registration,candidate_sha256:artifact,selected:false,authority:'none',production_authorized:false,
    stage_review:state,visual:{artifact_sha256:artifact,decision:'accepted',technical_override:false,
      applies_to_other_candidates:false,production_authorized:false}};
  const report={baseline_sha256:baseline,authority:'none',rows:[row]};
  assert.equal(relatedSummary(report,baseline)[0].visual,'阶段记录已撤销');
  state.current_applies=false;assert.match(relatedSummary(report,baseline)[0].visual,/当前证据需复核/);
  state.current.registration_sha256=second;assert.throws(()=>relatedSummary(report,baseline));
});

test('saving related review during a cohort read invalidates only related status, including late replies',async()=>{
  const listeners=new Map();globalThis.window={addEventListener:(type,listener)=>listeners.set(type,listener)};
  let release,notify;const started=new Promise(resolve=>notify=resolve);
  const pending=new Promise(resolve=>release=resolve);
  globalThis.fetch=async url=>({ok:true,json:async()=>{
    if(url==='/api/motions/source')return {status:'succeeded',source_sha256:'source-sha'};
    if(url==='/api/motions/motion-test')return {...job,kind:'adapt',status:'succeeded'};
    if(url.endsWith('/stage-review'))return {...baseState(),readiness:{...baseState().readiness,status:'needs_changes'}};
    notify();return pending;
  }});
  const root=new Node('main');createCohortStatus(root,{groups:[{job_id:'source',source_sha256:'source-sha',
    label:'下蹲',targets:[{job_id:job.job_id,artifact_sha256:artifact,label:'Alice'}]}]},()=>{});
  const reading=find(root,'核对全部候选状态').onclick();await started;
  const stats=()=>walk(root).find(n=>n.attrs['aria-label']==='交付状态统计').textContent;
  const before=stats();assert.match(before,/需处理技术异常 1\/1/);
  listeners.get('motion-related-review-saved')({detail:{jobId:job.job_id,registration}});
  release({baseline_sha256:artifact,authority:'none',rows:[]});await reading;
  assert.equal(stats(),before);
  assert.ok(walk(root).some(n=>n.textContent==='改进候选阶段结论已更新，请重新核对'));
  assert.ok(walk(root).some(n=>n.textContent.includes('有效阶段接受 0/1')));
});
