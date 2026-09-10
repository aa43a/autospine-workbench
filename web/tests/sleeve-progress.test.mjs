import test from 'node:test';
import assert from 'node:assert/strict';
import { sleeveProgress } from '../modules/sleeve-progress.js';
test('running repair shows eight completed stages, not a completion claim',()=>{
 const p=sleeveProgress({status:'running',step:'repair: running'});
 assert.equal(p.count,8);assert.equal(p.stages[8].state,'current');assert.match(p.label,/自动修正/);
});
test('failed and unknown stages do not appear completed',()=>{
 assert.match(sleeveProgress({status:'failed',step:'repair: running'}).label,/失败/);
 assert.equal(sleeveProgress({status:'running',step:'unknown: running'}).count,0);
 assert.equal(sleeveProgress(null).count,0);
});
test('terminal progress uses actual stage inventory and keeps review state',()=>{
 const p=sleeveProgress({status:'needs_review',result:{steps:[{id:'weights',status:'succeeded'}]}});
 assert.equal(p.total,1);assert.equal(p.count,1);assert.match(p.label,/复核/);
});
