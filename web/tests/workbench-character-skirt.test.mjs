import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkbenchCharacter} from '../modules/workbench-character.js';

const flush=()=>new Promise(resolve=>setImmediate(resolve));
test('residual preservation survives refresh and restores the saved build choice',async()=>{
 const calls=[];const f=fixture(async(url,init)=>{calls.push(init);return init.method==='POST'?job('running',{residual_auto_profile:'preserve'}):overview(job('needs_review',{residual_auto_profile:'preserve'}));});
 f.view.sync();await flush();
 const toggle=f.all.find(n=>n.attrs['aria-label']==='自动隐藏极低透明度残余');
 assert.equal(toggle.checked,false);
 toggle.checked=true;toggle.onchange();await f.view.refresh();assert.equal(toggle.checked,true);
 toggle.checked=false;toggle.onchange();f.build.events.click();await flush();
 assert.equal(JSON.parse(calls.find(c=>c.method==='POST').body).residual_auto_profile,'preserve');
 f.context.projectId=null;f.view.sync();assert.equal(toggle.checked,true);f.view.dispose();
});
test('whole build sends only the explicitly selected shoulder',async()=>{
 const calls=[];
 const f=fixture(async(url,init)=>{calls.push(init);return init.method==='POST'?job('running'):overview(job('needs_review',{
   layers:[{name:'handwear-l',regions:[{region_id:'layer-004',state:'weighted_candidate'}]},
    {name:'handwear-r',regions:[{region_id:'layer-003',state:'weighted_candidate'}]}]}));});
 f.view.sync();await flush();
 const left=descendants(f.view.element).find(n=>n.attrs['aria-label']==='修复左肩 · layer-004');
 left.checked=true;left.onchange();f.build.events.click();await flush();
 assert.deepEqual(JSON.parse(calls.find(c=>c.method==='POST').body).shoulder_regions,['layer-004']);
 f.view.dispose();
});
test('final exclusions rebuild with the exact saved recipe including legacy skirt profile',async()=>{
 const calls=[],recipe={skirt_profile:'fixed-waist-three-chain-v1',residual_texture_profile:'aligned-low-alpha-v1'};
 const f=fixture(async(url,init)=>{calls.push(init);return init.method==='POST'?job('running'):{...overview(job()),final_region_exclusions:{active:true,review:{decisions:[{region_id:'r'}],build_options:recipe}}};});
 f.view.sync();await flush();assert.equal(f.toggle.checked,true);assert.equal(f.toggle.disabled,true);
 f.build.events.click();await flush();const sent=JSON.parse(calls.find(c=>c.method==='POST').body);
 assert.equal(sent.skirt_profile,recipe.skirt_profile);assert.equal(sent.residual_texture_profile,recipe.residual_texture_profile);
 f.view.dispose();
});
const descendants=n=>[n,...(n.children||[]).flatMap(descendants)];
const job=(status='needs_review',extra={})=>({schema:'autospine.character-web-job/v1',project_id:'one',
 authority:'none',job_id:'job-'+'b'.repeat(32),status,stage:'review',layers:[],...extra});
const overview=current=>({project_id:'one',authority:'none',can_build:true,job:current,
 expected_resolved_sha256:'a'.repeat(64),expected_input_sha256:'c'.repeat(64),sleeve_job_id:'sleeve-one'});
function fixture(api){
 const document={createElement(tag){return {tag,children:[],attrs:{},events:{},
  append(...nodes){this.children.push(...nodes);},replaceChildren(...nodes){this.children=nodes;},
  setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];},addEventListener(k,v){this.events[k]=v;}};}};
 const context={projectId:'one',resolvedSha:'a'.repeat(64)};
 const view=createWorkbenchCharacter(document,{context:()=>context,apiRequest:api},{setTimeout(){return 1;},clearTimeout(){}});
 const all=descendants(view.element);
 return {view,context,all,toggle:all.find(n=>n.attrs['aria-label']==='生成裙装可变形候选'),
  build:all.find(n=>n.textContent==='构建整角色候选'),status:all.find(n=>n.attrs.role==='status')};
}

test('unchecked skirt leaves the original build request bytes and options unchanged',async()=>{
 const calls=[];const f=fixture(async(url,init)=>{calls.push([url,init]);return init.method==='POST'?job('running'):overview(job());});
 f.view.sync();await flush();assert.equal(f.toggle.checked,false);
 assert.ok(f.all.some(n=>n.textContent==='腰部与裙摆待复核，保留原纹理和原决定'));
 f.build.events.click();await flush();
 assert.deepEqual(calls.find(([,init])=>init.method==='POST'),['/api/projects/one/automation/character',{
  method:'POST',headers:{'X-Autospine-Intent':'pipeline-preview'},
  body:JSON.stringify({expected_resolved_sha256:'a'.repeat(64),expected_input_sha256:'c'.repeat(64),sleeve_job_id:'sleeve-one',residual_auto_profile:'low-alpha-residual-v1'})}]);
 f.view.dispose();
});

test('checked skirt adds only its explicit profile and resets across project identities',async()=>{
 const calls=[];const f=fixture(async(url,init)=>{calls.push(init);return init.method==='POST'?job('running'):overview(job());});
 f.view.sync();await flush();f.toggle.checked=true;f.toggle.onchange();f.build.events.click();await flush();
 assert.deepEqual(JSON.parse(calls.find(init=>init.method==='POST').body),{
  expected_resolved_sha256:'a'.repeat(64),expected_input_sha256:'c'.repeat(64),sleeve_job_id:'sleeve-one',
  skirt_profile:'reviewed-torso-waist-v2',residual_auto_profile:'low-alpha-residual-v1'});
 assert.equal(f.toggle.disabled,true);f.context.projectId=null;f.view.sync();assert.equal(f.toggle.checked,false);f.view.dispose();
});

test('skirt checkbox disables during request, dirty edits and active jobs',async()=>{
 let release;const f=fixture(()=>new Promise(resolve=>{release=resolve;}));
 f.view.sync();assert.equal(f.toggle.disabled,true);release(overview(job()));await flush();
 assert.equal(f.toggle.disabled,false);
 for(const flag of ['dirty','saving','loading']){
  f.context[flag]=true;f.view.sync();assert.equal(f.toggle.disabled,true);
  f.context[flag]=false;f.view.sync();assert.equal(f.toggle.disabled,false);
 }
 f.view.dispose();
});

test('skirt stage and numeric success remain explicitly pending visual review',async()=>{
 const current=job('running',{stage:'skirt-trial'});const f=fixture(async()=>overview(current));
 f.view.sync();await flush();assert.match(f.status.textContent,/正在生成裙装可变形候选/);
 assert.equal(f.toggle.disabled,true);
 current.status='needs_review';current.stage='review';
 current.skirt_trial={profile:'fixed-waist-three-chain-v1',layer_ids:['skirt'],geometry_passed:true,setup_error_px:0,authority:'none'};
 await f.view.refresh();assert.match(f.status.textContent,/裙装候选：采样网格检查通过，腰部与裙摆待复核/);
 assert.doesNotMatch(f.status.textContent,/已采用|自动采用|视觉通过/);
 current.skirt_trial.geometry_passed=false;await f.view.refresh();
 assert.match(f.status.textContent,/裙装候选：网格检查未通过，腰部与裙摆待复核/);f.view.dispose();
});
