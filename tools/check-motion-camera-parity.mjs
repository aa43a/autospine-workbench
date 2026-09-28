import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {solveCamera} from '../web/modules/motion-camera-solver.js';
const folder=process.argv[2];const read=name=>JSON.parse(fs.readFileSync(path.join(folder,name)));
const source=read('editor-source.json'),base=read('base-skeleton.json'),rows=[];
for(const name of ['fixed','turn']){
  const camera=read(`${name}-camera.json`),expected=read(`${name}-skeleton.json`).animations['camera-preview'];
  const start=performance.now(),actual=solveCamera(base,source,camera.keys);const elapsed=performance.now()-start;
  let maximum=0,values=0;
  assert.deepEqual(Object.keys(actual.animation.bones).sort(),Object.keys(expected.bones).sort());
  for(const [bone,tracks] of Object.entries(expected.bones))for(const [kind,keys] of Object.entries(tracks)){
    const found=actual.animation.bones[bone][kind];assert.equal(found.length,keys.length);
    keys.forEach((key,i)=>{for(const field of Object.keys(key)){const error=Math.abs(key[field]-found[i][field]);
      assert.ok(Number.isFinite(error),`${bone}/${kind}/${field}`);maximum=Math.max(maximum,error);values++;}});
  }
  assert.ok(maximum<1e-8,`${name} backend mismatch ${maximum}`);
  assert.deepEqual(actual,solveCamera(base,source,camera.keys));
  rows.push({name,maximum_parameter_error:maximum,values,elapsed_ms:elapsed});
}
fs.writeFileSync(path.join(folder,'browser-solver-parity.json'),JSON.stringify({passed:true,rows},null,2));
console.log(JSON.stringify(rows));
