import test from 'node:test';
import assert from 'node:assert/strict';
import {transformLayerVertices,normalizeLayerEdits,pointInLayer,canvasWorldPoint,canvasContentRect,layerBounds} from '../modules/motion-layer-transform.js';

test('world affine scales about fixed setup pivot then rotates CCW and translates',()=>{
  const edit={dx:3,dy:-2,rotation:90,scaleX:2,scaleY:.5};
  const actual=transformLayerVertices([12,20,10,24],edit,[10,20]);
  assert.deepEqual(actual.map(x=>Math.round(x*1e8)/1e8),[13,22,11,18]);
  // Animated geometry uses the same setup pivot, not its moving bounds center.
  assert.deepEqual(transformLayerVertices([13,20],edit,[10,20]).map(Math.round),[13,24]);
});
test('identity leaves geometry and original arrays untouched',()=>{
  const points=new Float32Array([2,3,4,5]);
  assert.deepEqual(transformLayerVertices(points,{dx:0,dy:0,rotation:0,scaleX:1,scaleY:1},[3,4]),[2,3,4,5]);
  assert.deepEqual(Array.from(points),[2,3,4,5]);
});
test('strict corrections reject incomplete order, unknown layers, duplicate edits and bad scale',()=>{
  const edit={slot:'arm',dx:0,dy:0,rotation:0,scaleX:1,scaleY:1};
  const value={profile:'slot-world-affine-v1',transforms:[edit],draw_order:['head','arm']};
  assert.deepEqual(normalizeLayerEdits(value,['arm','head']),value);
  assert.deepEqual(normalizeLayerEdits(value),value);
  assert.throws(()=>normalizeLayerEdits({...value,draw_order:['arm']},['arm','head']));
  assert.throws(()=>normalizeLayerEdits(value,['arm','body']));
  assert.throws(()=>normalizeLayerEdits({...value,transforms:[edit,edit]}));
  assert.throws(()=>normalizeLayerEdits({...value,transforms:[{...edit,scaleX:0}]}));
  assert.throws(()=>normalizeLayerEdits({...value,transforms:[{...edit,dx:Infinity}]}));
  assert.throws(()=>normalizeLayerEdits({...value,transforms:[null]}));
  const clone=normalizeLayerEdits(value);clone.transforms[0].dx=20;assert.equal(value.transforms[0].dx,0);
});
test('object-fit contain hit mapping rejects vertical letterbox and preserves world axes',()=>{
  const rect={left:100,top:50,width:400,height:500},bounds={left:-100,bottom:-200,width:800,height:600};
  assert.deepEqual(canvasContentRect(rect,800,600),{left:100,top:150,width:400,height:300,scale:.5});
  assert.equal(canvasWorldPoint(300,100,rect,bounds),null);
  assert.deepEqual(canvasWorldPoint(300,300,rect,bounds),{x:300,y:100});
  assert.deepEqual(canvasWorldPoint(100,150,rect,bounds),{x:-100,y:400});
});
test('triangle hit test ignores bounding-box empty space and degenerate triangles',()=>{
  const points=[0,0,4,0,0,4];assert.equal(pointInLayer({x:1,y:1},points,[0,1,2]),true);
  assert.equal(pointInLayer({x:3,y:3},points,[0,1,2]),false);
  assert.equal(pointInLayer({x:0,y:0},points,[0,0,0]),false);
  assert.deepEqual(layerBounds(points),{left:0,right:4,bottom:0,top:4,width:4,height:4});
});
