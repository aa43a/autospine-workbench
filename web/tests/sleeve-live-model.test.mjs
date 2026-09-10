import test from 'node:test';
import assert from 'node:assert/strict';
import {sleeveLivePoints,sleeveLiveAngles} from '../modules/sleeve-live-model.js';
const bones=[{id:'upper',head_xy:[0,0]},{id:'forearm',head_xy:[10,0]},{id:'hand',head_xy:[20,0]}];
const record={bone_ids:['upper','forearm','hand'],vertices_xy:[[21,0],[22,0],[21,1]],triangles:[[0,1,2]]};
const mesh={weights:record.vertices_xy.map(()=>[{bone_id:'hand',weight:1}])};
const assignments=role=>[{role}];
test('setup preserved for every draft role',()=>{
  for(const role of ['hand','cuff','sleeve','hanging_cloth','unknown'])
    assert.deepEqual(sleeveLivePoints(record,assignments(role),bones,mesh,[0,0,0,0]),record.vertices_xy);
});
test('editing sleeve to hand changes current pose without modifying sources',()=>{
  const saved=JSON.stringify({record,mesh});
  const sleeve=sleeveLivePoints(record,assignments('sleeve'),bones,mesh,[0,0,90,0]);
  const hand=sleeveLivePoints(record,assignments('hand'),bones,mesh,[0,0,90,0]);
  assert.deepEqual(sleeve,record.vertices_xy);assert.ok(Math.abs(hand[0][0]-20)<1e-9);assert.ok(Math.abs(hand[0][1]-1)<1e-9);
  assert.equal(JSON.stringify({record,mesh}),saved);
});
test('unknown shared vertex is preserved under optional rigid hand trial',()=>{
  const r={...record,vertices_xy:[...record.vertices_xy,[22,1]],triangles:[[0,1,2],[1,3,2]]};
  const m={weights:r.vertices_xy.map(()=>[{bone_id:'forearm',weight:1}])};
  const p=sleeveLivePoints(r,[{role:'hand'},{role:'unknown'}],bones,m,[0,0,90,0],true);
  assert.deepEqual(p.slice(1),r.vertices_xy.slice(1));assert.notDeepEqual(p[0],r.vertices_xy[0]);
});
test('cloth drive follows wrist and has a closed loop',()=>{
  const a=sleeveLivePoints(record,assignments('hanging_cloth'),bones,mesh,[0,90,0,90]);
  assert.ok(Math.abs(a[0][0]-9)<1e-9);assert.ok(Math.abs(a[0][1]-10)<1e-9);
  assert.ok(sleeveLiveAngles(2,'combined').every(v=>Math.abs(v)<1e-12));
});
