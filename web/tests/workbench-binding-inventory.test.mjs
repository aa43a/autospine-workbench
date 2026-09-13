import test from 'node:test';
import assert from 'node:assert/strict';
import {boneLabel,bindingInventoryRows} from '../modules/workbench-binding-inventory.js';
const doc={createElement(tag){return {tag,children:[],append(...v){this.children.push(...v);},setAttribute(){}};}};
const all=n=>[n,...n.children.flatMap(all)];
test('shows actual side and cloth influences without a correctness claim',()=>{
 assert.equal(boneLabel('upperarm_l'),'左上臂');assert.equal(boneLabel('cloth-layer-1'),'衣料辅助骨');
 const rows=bindingInventoryRows(doc,{schema:'autospine.weighted-binding-inventory/v1',authority:'none',regions:[
  {layer_id:'arm',region_id:'part',vertex_count:2,influences:[{bone:'forearm_r',vertex_count:2,min_weight:.25,max_weight:1}]}]},'arm');
 assert.match(rows[0].children[0].textContent,/右前臂/);
 assert.ok(all(rows[0]).some(n=>n.textContent?.includes('25.0%–100.0%')));
 assert.ok(all(rows[0]).some(n=>n.textContent?.includes('不是语义正确率')));
 assert.deepEqual(bindingInventoryRows(doc,{authority:'none',regions:[]},'arm'),[]);
});
