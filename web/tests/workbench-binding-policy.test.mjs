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
test('explicit check exposes eligible count and apply refreshes parent',async()=>{
  let request;
  const f=fixture(async(url,init)=>{request=init;return{...response(),operation:{changed:init.method==='POST'}};});
  assert.equal(f.buttons[1].disabled,true);await f.view.request();assert.equal(f.buttons[1].disabled,false);
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
  assert.equal(f.buttons[1].disabled,true);assert.doesNotMatch(f.status.textContent,/可自动绑定 1/);
});
test('source identity change discards old policy and undo',async()=>{
 const f=fixture(async()=>({...response(),active_decision_sha256:'c'.repeat(64)}));await f.view.request();assert.equal(f.buttons[2].disabled,false);
 f.model.inputIdentitySha='d'.repeat(64);f.view.sync(f.model);assert.equal(f.buttons[2].disabled,true);
});
