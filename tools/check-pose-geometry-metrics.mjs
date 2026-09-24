import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const code=await fs.readFile('web/modules/pose-geometry-metrics.js','utf8');
const {createGeometryMetrics}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
const setup=[[0,0],[1,0],[0,1],[1,1]],triangles=[[0,1,2],[1,3,2]];
const measure=createGeometryMetrics(setup,triangles);
assert.equal(measure(setup).passed,true);
// Unit determinant stretching preserves every triangle area, but is not safe.
const skinny=measure(setup.map(([x,y])=>[x*3,y/3]));
assert.deepEqual(skinny.badTriangles,[]);
assert.equal(skinny.maxEdgeStretch,3);
assert.equal(skinny.passed,false);
assert.ok(skinny.badEdges.length>0);
// Translation and rotation preserve setup-space metrics.
const rigid=measure(setup.map(([x,y])=>[10-y,20+x]));
assert.equal(rigid.passed,true);
assert.equal(rigid.maxEdgeStretch,1);
assert.equal(measure(setup.map(([x,y])=>[-x,y])).inversions,2);
assert.equal(measure(setup.map(([x,y])=>[x*.1,y])).badTriangles.length,2);
assert.throws(()=>measure([[NaN,0],...setup.slice(1)]));
assert.throws(()=>createGeometryMetrics([[0,0],[0,0],[0,1]],[[0,1,2]]));
console.log('Geometry diagnostics: area-preserving stretch, rigid invariance, inversion, compression and invalid data passed');
