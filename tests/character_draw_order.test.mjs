import assert from 'node:assert/strict';
import '../tools/character-draw-order.js';
const doc={slots:['a','b','c'].map(name=>({name})),animations:{move:{drawOrder:[
  {time:0.1,offsets:[{slot:'a',offset:2}]},{time:0.2}]}}};
const order=globalThis.autospineExpectedDrawOrder;
assert.deepEqual(order(doc,'move',0),['a','b','c']);
assert.deepEqual(order(doc,'move',Math.fround(.1)),['b','c','a']);
assert.deepEqual(order(doc,'move',.1),['a','b','c']);
assert.deepEqual(order(doc,'move',Math.fround(.2)),['a','b','c']);
assert.deepEqual(order(doc,null,.3),['a','b','c']);
doc.animations.move.drawOrder=[{time:0,offsets:[{slot:'a',offset:1},{slot:'b',offset:-1},{slot:'c',offset:0}]}];
assert.deepEqual(order(doc,'move',0),['b','a','c']);
console.log('draw-order reconstruction and Float32 boundaries passed');
