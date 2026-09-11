import test from 'node:test';
import assert from 'node:assert/strict';
import { sleeveProgress } from '../modules/sleeve-progress.js';
test('stale source is distinguished from an absent task or geometry failure',()=>{
 for(const reason_code of ['project_snapshot_stale','sleeve_draft_changed','sleeve_annotation_required','sleeve_source_check_failed']) {
  const p=sleeveProgress({status:'blocked',reason_code});
  assert.match(p.label,/已有任务需要更新来源/);
  assert.equal(p.count,0);
  assert.ok(p.stages.every(s=>s.state==='pending'));
 }
});
test('ordinary plan excludes cloth steps from in-progress counts',()=>{
 const p=sleeveProgress({status:'running',step:'spine: running',stage_ids:['weights','spine','contacts','overlap','runtime']});
 assert.equal(p.total,5);assert.equal(p.count,1);assert.equal(p.stages.length,5);
 assert.equal(p.stages[1].state,'current');assert.match(p.label,/导出/);
 assert.ok(!p.stages.some(s=>s.name.includes('根部')));
});
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

test('ordinary correction stages preserve graph order and parse hyphenated progress',()=>{
 const stage_ids=['weights','ordinary-repair','ordinary-deform','ordinary-interpolation','spine','contacts','overlap','runtime','framebuffer'];
 const p=sleeveProgress({status:'running',step:'ordinary-deform: running',stage_ids});
 assert.equal(p.total,9);assert.equal(p.count,2);
 assert.equal(p.stages[2].state,'current');assert.match(p.label,/修正普通袖局部变形/);
 assert.match(p.stages[3].name,/帧间过渡/);
 assert.ok(!p.stages.some(s=>s.name.includes('驱动根部')));
 const done=sleeveProgress({status:'blocked',result:{steps:stage_ids.map(id=>({id,status:'succeeded'}))}});
 assert.equal(done.count,9);assert.match(done.label,/未通过/);
});
