import assert from 'node:assert/strict';
import {createShoulderRepair,applyCharacterRecipe} from '../web/modules/workbench-character-shoulder.js';
const nodes=[];
const document={createElement:tag=>{
  const node={tag,textContent:'',children:[],append(...items){this.children.push(...items);},setAttribute(){}};
  nodes.push(node);return node;
}};
const panel=createShoulderRepair(document);
const text=()=>nodes.map(n=>n.textContent).join('\n');
panel.sync(null,{shoulder_regions:['layer-004']},false);
assert.deepEqual(panel.payload(),{});
assert(!nodes.some(n=>['input','button'].includes(n.tag)));
assert(text().includes('历史方案含旧肩部约束'));
panel.sync({shoulder_trial:{included_in_candidate:true}},null,false);
assert(text().includes('尚未回退'));
panel.sync({shoulder_trial:{reason_code:'shoulder_boundary_constraint_retired'}},null,false);
assert(text().includes('几何与 Runtime 检查仍独立执行'));
panel.reset();assert(!text().includes('尚未回退'));
const recipe={shoulder_regions:['layer-004'],skirt_profile:'existing'};
const overview={order_review:{active:true,review:{build_options:recipe}}};
assert.deepEqual(applyCharacterRecipe({},overview),recipe); // History is not silently rewritten.
console.log('Passed: retired controls, no new pin request, truthful history and preserved recipe');
