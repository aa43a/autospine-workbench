import test from 'node:test';
import assert from 'node:assert/strict';
import { createWorkbenchCharacter } from '../modules/workbench-character.js';

const flush = () => new Promise(resolve => setImmediate(resolve));
const descendants=node=>[node,...(node.children||[]).flatMap(descendants)];
function fixture(api) {
  const document = {createElement(tag) {return {tag, children:[],events:{},attrs:{},
    append(...nodes){this.children.push(...nodes);},replaceChildren(...nodes){this.children=nodes;},
    setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];},
    addEventListener(k,v){this.events[k]=v;}};}};
  const context={projectId:'one',resolvedSha:'a'.repeat(64)}, timers=new Map();
  const view=createWorkbenchCharacter(document,{context:()=>context,apiRequest:api},{
    setTimeout(fn){const key=Symbol();timers.set(key,fn);return key;},clearTimeout(key){timers.delete(key);}});
  const [,,actions,status,download]=view.element.children;
  const details=view.element.children.find(n=>n.tag==='details');
  return {view,context,timers,status,download,details,build:actions.children[0]};
}
const job=(status='needs_review')=>({schema:'autospine.character-web-job/v1',project_id:'one',authority:'none',
  job_id:'job-'+ 'b'.repeat(32),status,stage:status==='running'?'compose':'review',layers:[]});
const overview=value=>({project_id:'one',authority:'none',can_build:true,job:value});

test('static region links require inventoried report and safe anchor',async()=>{
  const current=job();current.layers=[{layer_id:'source',name:'cloth',state:'partial'}];
  current.runtime={files:{'static-regions/index.html':'a'},static_region_links:{source:[
    'static-regions/index.html#region-0','https://invalid/#region-1','static-regions/index.html#bad']}};
  const f=fixture(async()=>overview(current));f.view.sync();await flush();
  const links=descendants(f.details.children[2].children[0]).filter(n=>n.tag==='a');
  assert.equal(links.length,1);assert.match(links[0].attrs.href,/\/view\/static-regions\/index.html#region-0$/);
  f.view.dispose();
});

test('exclusion sends exact current region and revision then refreshes',async()=>{
  const current=job();current.artifact_sha256='c'.repeat(64);
  current.layers=[{layer_id:'source',name:'cloth',state:'partial',regions:[{region_id:'rest',state:'static_reference'}]}];
  const calls=[];const f=fixture(async(url,init)=>{calls.push([url,init]);return {...overview(current),region_exclusions:{head_sha256:null,active:[]}};});
  f.view.sync();await flush();
  const button=descendants(f.details.children[2].children[0]).find(n=>n.textContent==='排除静态区域 rest');
  await button.onclick();await flush();
  const write=calls.find(([url])=>url.endsWith('/regions'));
  assert.deepEqual(JSON.parse(write[1].body),{action:'exclude',job_id:current.job_id,expected_artifact_sha256:current.artifact_sha256,
    layer_id:'source',region_id:'rest',expected_head_sha256:null});
  assert.equal(calls.length,3);f.view.dispose();
});

test('motion selector sends an available choice and clears on project change',async()=>{
  const choice='e'.repeat(64),calls=[];
  const f=fixture(async(url,init)=>{calls.push([url,init]);return init.method==='POST'?job('running'):
    {...overview(job()),motion_choices:[{choice_id:choice,animations:['walk'],available:true}]};});
  f.view.sync();await flush();
  const select=f.view.element.children[2].children.find(n=>n.tag==='label').children[0];
  assert.equal(select.disabled,false);select.value=choice;select.onchange();
  f.build.events.click();await flush();
  assert.equal(JSON.parse(calls.find(([,init])=>init.method==='POST')[1].body).motion_choice_id,choice);
  f.context.projectId=null;f.view.sync();assert.equal(select.value,'');f.view.dispose();
});

test('restored terminal candidate stops polling and dirty edits suppress download',async()=>{
  const f=fixture(async()=>overview(job()));f.view.sync();await flush();
  assert.equal(f.download.hidden,false);assert.equal(f.timers.size,0);
  assert.match(f.download.attrs.href,/\/one\/automation\/character\/jobs\/job-/);
  f.context.dirty=true;f.view.sync();assert.equal(f.download.hidden,true);
  assert.equal(f.build.disabled,true);assert.equal(f.download.attrs.href,undefined);
  f.view.dispose();
});

test('poll retains meaningful stage then stops on terminal response',async()=>{
  let calls=0;const f=fixture(async()=>++calls===1?overview(job('running')):job());
  f.view.sync();await flush();assert.match(f.status.textContent,/合并袖装/);
  assert.equal(f.timers.size,1);const [key,run]=[...f.timers][0];f.timers.delete(key);run();await flush();
  assert.equal(calls,2);assert.equal(f.timers.size,0);assert.equal(f.download.hidden,false);
  f.view.dispose();
});

test('late response from previous project cannot restore its download',async()=>{
  let release;const f=fixture(()=>new Promise(resolve=>{release=resolve;}));
  f.view.sync();f.context.projectId=null;f.view.sync();release(overview(job()));await flush();
  assert.equal(f.download.hidden,true);assert.equal(f.timers.size,0);
  assert.equal(f.details.hidden,true);assert.equal(f.build.disabled,true);f.view.dispose();
});

test('verified report links track current job and hide on unsaved edits',async()=>{
  const current=job();current.runtime={files:{'index.html':'a','setup/index.html':'b'}};
  const f=fixture(async()=>overview(current));f.view.sync();await flush();
  const [runtime,setup]=f.view.element.children.filter(n=>n.tag==='a').slice(-2);
  assert.equal(runtime.hidden,false);assert.match(setup.attrs.href,/\/view\/setup\/index.html$/);
  f.context.dirty=true;f.view.sync();assert.equal(runtime.hidden,true);assert.equal(setup.attrs.href,undefined);
  f.view.dispose();
});

test('character ledger distinguishes automatic binding and stale evidence',async()=>{
  const current=job();current.layers=[{layer_id:'face-detail',name:'mouth',state:'rigid_reviewed',
    binding_decision:{decision_source:'policy_auto',evidence_current:false}}];
  const f=fixture(async()=>overview(current));f.view.sync();await flush();
  const row=f.details.children[2].children[0];
  assert.match(row.children[1].textContent,/自动策略采用/);
  assert.match(row.children[1].textContent,/证据来源已变化/);f.view.dispose();
});

test('exception view separates output regions from pending layer decisions and retains full ledger',async()=>{
  const current=job();current.layers=[
    {layer_id:'head',name:'head',state:'rigid_reviewed',binding_decision:{decision_source:'explicit_selection'},regions:[{region_id:'head',state:'rigid_reviewed'}]},
    {layer_id:'arms',name:'arms',state:'weighted_candidate',binding_decision:{decision_source:'pending'},regions:[{region_id:'left-arm',state:'weighted_candidate'},{region_id:'right-arm',state:'weighted_candidate'}]},
    {layer_id:'shoe',name:'shoe',state:'partial',regions:[{region_id:'shoe-mesh',state:'weighted_candidate'},{region_id:'shoe-rest',state:'static_reference'}],excluded_regions:[{region_id:'removed'}]}
  ];
  const f=fixture(async()=>overview(current));f.view.sync();await flush();
  const [summary,controls,list]=f.details.children,select=controls.children[0].children[0];
  assert.equal(f.details.open,true);assert.match(summary.textContent,/待处理 2 \/ 全部 3/);
  assert.equal(list.children.length,2);
  assert.match(controls.children[1].textContent,/3 个加权区域、1 个刚性区域/);
  assert.ok(list.children[0].children.some(n=>n.textContent?.includes('已有加权区域')));
  assert.ok(descendants(list.children[0]).some(n=>n.textContent==='right-arm · 加权候选'));
  assert.ok(descendants(list.children[1]).some(n=>n.textContent==='removed · 已按区域决定排除'));
  select.value='all';select.onchange();assert.equal(list.children.length,3);
  assert.equal(current.layers.length,3);assert.equal(current.layers[1].binding_decision.decision_source,'pending');
  f.context.projectId=null;f.view.sync();assert.equal(select.value,'pending');f.view.dispose();
});
