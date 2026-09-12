import test from 'node:test';
import assert from 'node:assert/strict';
import {residualMessages} from '../modules/workbench-texture-residuals.js';
const layer={layer_id:'layer-1',regions:[{region_id:'rest'}]};
const job={status:'needs_review',texture_trial:{authority:'none',regions:[
 {layer_id:'layer-1',region_id:'rest',transferred_pixels:7,remaining_pixels:3,blocking_counts:{outside_mesh:2,uv_alignment_required:1}},
 {layer_id:'other',region_id:'rest',transferred_pixels:10,remaining_pixels:0},
 {layer_id:'layer-1',region_id:'old',transferred_pixels:10,remaining_pixels:0}]}};
test('explains only matching current regions and preserves residual',()=>{
 const result=residualMessages(job,layer);assert.equal(result.length,1);
 assert.match(result[0],/已归并 7 像素，保留 3/);
 assert.match(result[0],/网格外侧 2/);assert.match(result[0],/纹理坐标尚未对齐 1/);
 assert.match(result[0],/不会自动排除/);
});
test('old jobs and unavailable candidates do not invent counts',()=>{
 assert.deepEqual(residualMessages({status:'needs_review'},layer),[]);
 assert.deepEqual(residualMessages({...job,status:'blocked'},layer),[]);
});
test('zero remainder does not imply adoption',()=>{
 const j=structuredClone(job);j.texture_trial.regions[0].remaining_pixels=0;
 j.texture_trial.regions[0].blocking_counts={};
 assert.match(residualMessages(j,layer)[0],/绑定及视觉确认仍需复核/);
});
