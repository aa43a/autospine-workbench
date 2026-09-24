import test from 'node:test';
import assert from 'node:assert/strict';
import {brushTriangles} from '../modules/mesh-brush.js';
const mesh={uvs:[0,0,1,0,0,1],triangles:[0,1,2]};
test('click near large triangle corner succeeds even far from centroid',()=>{
  assert.deepEqual(brushTriangles(mesh,100,100,[2,2],[2,2],2),[0]);
});
test('stroke crossing triangle selects even with both events outside',()=>{
  assert.deepEqual(brushTriangles(mesh,100,100,[-10,40],[110,40],1),[0]);
});
test('near edge radius intersects but distant and collinear extension do not',()=>{
  assert.deepEqual(brushTriangles(mesh,100,100,[50,-3],[60,-3],3),[0]);
  assert.deepEqual(brushTriangles(mesh,100,100,[50,-4],[60,-4],3),[]);
  assert.deepEqual(brushTriangles(mesh,100,100,[120,0],[130,0],1),[]);
});
test('degenerate UV triangles are not selected everywhere',()=>{
  assert.deepEqual(brushTriangles({uvs:[0,0,0,0,0,0],triangles:[0,1,2]},100,100,[40,40],[40,40],5),[]);
});
test('non-square scaling and invalid input',()=>{
  assert.deepEqual(brushTriangles(mesh,200,20,[100,5],[100,5],0),[0]);
  assert.throws(()=>brushTriangles(mesh,100,100,[NaN,0],[1,1],2));
});
