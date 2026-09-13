import test from 'node:test';
import assert from 'node:assert/strict';
import {createBindingPolicy} from '../modules/workbench-binding-policy.js';
function fixture(api){
  const document={createElement(tag){return{tag,children:[],events:{},append(...n){this.children.push(...n);},replaceChildren(...n){this.children=n;},setAttribute(){},addEventListener(k,f){this.events[k]=f;}};}};
  const context={projectId:'one',resolvedSha:'a'.repeat(64)},model={canReview:true,inputIdentitySha:'b'.repeat(64)};
  let saved=0;
  const view=createBindingPolicy(document,{context:()=>context,apiRequest:api,locate(){},saved(){saved++;}});
  view.sync(model);
  return{view,context,model,get saved(){return saved;},buttons:view.element.children[2].children,status:view.element.children[3]};
}
const response=()=>({schema:'autospine.binding-policy-overview/v1',authority:'none',project_id:'one',
 source_addresses:{resolved_project_sha256:'a'.repeat(64),input_identity_sha256:'b'.repeat(64)},rows:[{layer_id:'shoe',status:'eligible',name:'shoe',option_id:'rigid:foot_l',reason_codes:[],checks:{}}]});
test('prerequisite explanation does not imply dependent automatic adoption',async()=>{
 const f=fixture(async()=>({...response(),rows:[{layer_id:'eye',name:'眼',status:'needs_review',reason_codes:['policy_capability_unsupported'],checks:{}},
  {layer_id:'face',name:'脸',status:'needs_review',reason_codes:['face_above_neck'],checks:{}}],
  review_focus:[{reason_code:'head_details_require_face_binding',prerequisite_layer_ids:['face'],dependent_layer_ids:['eye'],automatic_adoption_guaranteed:false}]}));
 await f.view.request();
 const text=n=>[n.textContent||'',...n.children.map(text)].join(' ');
 assert.match(text(f.view.element),/先复核下列前置层/);assert.match(text(f.view.element),/不保证自动通过/);
 assert.match(text(f.view.element),/等待脸层绑定/);assert.match(text(f.view.element),/面部跨入颈点以下/);
 assert.doesNotMatch(text(f.view.element),/当前策略不支持此部件/);
 f.model.inputIdentitySha='d'.repeat(64);f.view.sync(f.model);
 assert.doesNotMatch(text(f.view.element),/等待脸层绑定/);
});
test('explicit check exposes eligible count and apply refreshes parent',async()=>{
  let request;
  const f=fixture(async(url,init)=>{request=init;return{...response(),operation:{changed:init.method==='POST'}};});
  assert.equal(f.buttons[1].disabled,false);await f.view.request();assert.equal(f.buttons[1].disabled,false);
  await f.view.request('apply');assert.equal(JSON.parse(request.body).expected_input_sha256,'b'.repeat(64));assert.equal(f.saved,1);
});
test('dirty edits and missing undo identity prevent mutation',async()=>{
  let calls=0;const f=fixture(async()=>{calls++;return response();});
  await f.view.request('undo');assert.equal(calls,0);
  f.model.bindingDirty=true;f.view.sync(f.model);await f.view.request();assert.equal(calls,0);assert.equal(f.buttons[0].disabled,true);
});
test('late response cannot enter a different project',async()=>{
  let release;const f=fixture(()=>new Promise(r=>{release=r;}));const p=f.view.request();
  f.context.projectId='two';f.view.sync(f.model);release(response());await p;
  assert.equal(f.buttons[1].disabled,false);assert.doesNotMatch(f.status.textContent,/可自动绑定 1/);
});
test('source identity change discards old policy and undo',async()=>{
 const f=fixture(async()=>({...response(),active_decision_sha256:'c'.repeat(64)}));await f.view.request();assert.equal(f.buttons[2].disabled,false);
 f.model.inputIdentitySha='d'.repeat(64);f.view.sync(f.model);assert.equal(f.buttons[2].disabled,true);
});
test('undo submits the selected older batch rather than the latest batch',async()=>{
 let body;
 const newer='c'.repeat(64),older='d'.repeat(64);
 const f=fixture(async(url,init)=>{if(init.method==='POST')body=JSON.parse(init.body);return {...response(),active_decision_sha256:newer,
  reversible_decisions:[{decision_sha256:newer,can_undo:true,layer_names:['shoe']},{decision_sha256:older,can_undo:true,layer_names:['eye']}]};});
 await f.view.request();f.buttons[3].value=older;await f.view.request('undo');
 assert.equal(body.decision_sha256,older);
});

test('one-click automatic run needs no prior check and reports each saved batch',async()=>{
 let body;const f=fixture(async(url,init)=>{body=JSON.parse(init.body);return {...response(),operation:{schema:'autospine.binding-auto-run/v1',changed:true,rounds:2,changed_layer_ids:['face','eye'],status:'succeeded'}};});
 await f.view.request('apply_all');assert.equal(body.action,'apply_all');assert.equal(f.saved,1);
 assert.match(f.status.textContent,/2 批、2 层/);
});

test('failed mutation refreshes committed state without replaying the request',async()=>{
 let calls=0;const f=fixture(async()=>{calls++;throw Error('connection lost');});
 await f.view.request('apply_all');assert.equal(f.saved,1);assert.equal(calls,1);
 assert.match(f.status.textContent,/核对已保存结果/);
});

test('primary button prepares missing candidates even with no eligible bindings',async()=>{
 let body;const f=fixture(async(url,init)=>{body=JSON.parse(init.body);return {...response(),rows:[],operation:{schema:'autospine.binding-auto-workflow/v1',changed:true,rounds:0,changed_layer_ids:[],status:'succeeded',candidate_preparation:{changed:true}}};});
 f.buttons[1].events.click();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(body.action,'prepare_apply_all');assert.equal(f.saved,1);
 assert.match(f.status.textContent,/已补齐绑定候选/);assert.match(f.status.textContent,/0 批、0 层/);
});
