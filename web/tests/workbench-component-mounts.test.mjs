import test from 'node:test';
import assert from 'node:assert/strict';
import {createComponentMounts} from '../modules/workbench-component-mounts.js';
const all=n=>[n,...n.children.flatMap(all)],flush=()=>new Promise(r=>setImmediate(r));
function fixture(api){
 const calls=[],document={createElement(tag){const n={tag,children:[],attrs:{},append(...v){this.children.push(...v);},replaceChildren(...v){this.children=v;},setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];},
 getContext(){return new Proxy({},{get:(_,key)=>key==='getImageData'?()=>({data:[0,0,0,150]}):()=>{}});}};
 if(tag==='img')Object.defineProperty(n,'src',{set(){queueMicrotask(()=>n.onload());}});return n;}};
 const view=createComponentMounts(document,{apiRequest:api,save:v=>calls.push(v)});return {view,calls};
}
const job={job_id:'job-a',status:'needs_review',artifact_sha256:'a',layers:[{layer_id:'wing',regions:[{region_id:'wing',state:'static_reference'}]}]};
const plan={schema:'autospine.component-mount-canvas/v1',authority:'none',job_id:'job-a',source_bundle_sha256:'a',source_region_id:'wing',plan_sha256:'p',width:100,height:100,image:'x',residual_pixels:1,
 allowed_parents:['head','chest'],bones:[{name:'head',point:[50,10]},{name:'chest',point:[50,60]}],parts:[{component_id:'part',bbox:[0,0,30,30],mask:'x',proposed_parent:'head',visible_pixels:100}]};
test('canvas selection stays a draft until explicit save and preserves source identity',async()=>{
 const f=fixture(async()=>plan);f.view.sync(job,null,'/one',false);
 await all(f.view.element).find(n=>n.textContent==='显示区域与骨架').onclick();await flush();
 assert.equal(f.calls.length,0);
 const select=all(f.view.element).find(n=>n.attrs['aria-label']==='part 的父骨骼');select.value='chest';select.onchange();
 all(f.view.element).find(n=>n.textContent==='确认映射并保存').onclick();
 assert.equal(f.calls[0].decision.parents.part,'chest');assert.equal(f.calls[0].decision.plan_sha256,'p');
 assert.equal(f.calls[0].decision.source_bundle_sha256,'a');
});
test('a response from a previous project cannot become a saveable draft',async()=>{
 let resolve;const f=fixture(()=>new Promise(r=>resolve=r));f.view.sync(job,null,'/one',false);
 all(f.view.element).find(n=>n.textContent==='显示区域与骨架').onclick();f.view.sync(null,null,'/two',false);resolve(plan);await flush();
 assert.equal(all(f.view.element).find(n=>n.textContent==='确认映射并保存').disabled,true);assert.equal(f.calls.length,0);
});

test('mixed garment distance suggestions are not saved as selected parents',async()=>{
 const f=fixture(async()=>({...plan,requires_parent_review:true}));f.view.sync(job,null,'/one',false);
 all(f.view.element).find(n=>n.textContent==='显示区域与骨架').onclick();await flush();
 const save=all(f.view.element).find(n=>n.textContent==='确认映射并保存');
 assert.equal(save.disabled,true);save.onclick();assert.equal(f.calls.length,0);
 const select=all(f.view.element).find(n=>n.attrs['aria-label']==='part 的父骨骼');
 assert.equal(select.value,'');assert.ok(select.children[0].textContent.includes('距离建议'));
 select.value='chest';select.onchange();assert.equal(save.disabled,false);save.onclick();
 assert.deepEqual(f.calls[0].decision.parents,{part:'chest'});
});
test('saved mapping can be revoked while source candidate is invalidated',()=>{
 const f=fixture();f.view.sync(null,{active:true,head_sha256:'h',review:{decision:{parents:{part:'head'}}}},'/one',false);
 assert.equal(f.view.element.hidden,false);all(f.view.element).find(n=>n.textContent==='撤销分区绑定').onclick();assert.deepEqual(f.calls,[{action:'revoke'}]);
});
test('running builds do not ask for another rebuild',()=>{
 const f=fixture();f.view.sync({status:'running'},{active:true,head_sha256:'h',review:{decision:{parents:{part:'head'}}}},'/one',true);
 assert.ok(all(f.view.element).some(n=>n.textContent.includes('整角色正在构建')));
 assert.equal(all(f.view.element).find(n=>n.textContent==='撤销分区绑定').disabled,true);
});
