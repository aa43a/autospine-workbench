import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {refineProjectedCamera} from '../web/modules/motion-projected-camera-sampling.js';
const folder=process.argv[2],read=n=>JSON.parse(fs.readFileSync(path.join(folder,n)));
const source=read('editor-source.json'),expected=read('projected-grid.json');
for(const row of expected.rows){
  const camera=read(`${row.name}-camera.json`);
  assert.deepEqual(refineProjectedCamera(source.times,source.vectors,camera.keys,source.duration,source.reference),row.times);
}
assert.throws(()=>refineProjectedCamera([0,1],{arm:[[1,0,0],[-1,0,0]]},[{time:0,yaw:0}],1,1),/unobservable/);
fs.writeFileSync(path.join(folder,'projected-grid-parity.json'),JSON.stringify({passed:true,cases:expected.rows.length}));
