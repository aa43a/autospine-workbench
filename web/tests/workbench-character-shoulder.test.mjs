import test from 'node:test';
import assert from 'node:assert/strict';
import {createShoulderRepair,applyCharacterRecipe} from '../modules/workbench-character-shoulder.js';
const document={createElement(tag){return {tag,children:[],attrs:{},append(...n){this.children.push(...n);},
  replaceChildren(...n){this.children=n;},setAttribute(k,v){this.attrs[k]=v;}};}};
const descendants=n=>[n,...n.children.flatMap(descendants)];
const job={layers:[{name:'handwear-l',regions:[{region_id:'layer-004',state:'weighted_candidate'}, {region_id:'residual',state:'static_reference'}]},
 {name:'handwear-r',regions:[{region_id:'layer-003',state:'weighted_candidate'}]},{name:'topwear',regions:[{region_id:'torso'}]}]};
test('opt-in only, selected side, clear and project reset',()=>{
 const ui=createShoulderRepair(document);ui.sync(job,null,false);
 assert.deepEqual(ui.payload(),{});
 const choices=descendants(ui.element).filter(e=>e.type==='checkbox');assert.equal(choices.length,2);
 choices[0].checked=true;choices[0].onchange();assert.deepEqual(ui.payload(),{shoulder_regions:['layer-004']});
 ui.sync({status:'running',stage:'shoulder-adaptive'},null,true);
 assert.ok(descendants(ui.element).filter(e=>e.type==='checkbox').every(e=>e.disabled));
 assert.ok(descendants(ui.element).some(e=>e.textContent==='正在检查并修正异常时间段'));
 ui.reset();ui.sync(job,null,false);assert.deepEqual(ui.payload(),{});
});
test('failed trial explains original retention and exact saved recipe locks selection',()=>{
 const ui=createShoulderRepair(document);
 ui.sync({...job,shoulder_trial:{status:'blocked'}},{shoulder_regions:['layer-003']},false);
 assert.deepEqual(ui.payload(),{shoulder_regions:['layer-003']});
 assert.ok(descendants(ui.element).some(e=>e.textContent.includes('保留原候选')));
 assert.ok(descendants(ui.element).filter(e=>e.type==='checkbox').every(e=>e.disabled));
});
test('latest order recipe overrides prior recipe without stale shoulder options',()=>{
 const overview={order_review:{active:true,review:{build_options:{skirt_profile:'old'}}},
 component_mounts:{active:true,review:{build_options:{shoulder_regions:['left']}}}};
 assert.deepEqual(applyCharacterRecipe({project:'p',shoulder_regions:['right']},overview),{project:'p',skirt_profile:'old'});
 const payload={project:'p'};assert.equal(applyCharacterRecipe(payload,{}),payload);
});
