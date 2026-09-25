import assert from 'node:assert/strict';
import {matchesVisual, visualNotes, visualState} from '../web/modules/motion-cohort-visual.js';
import {deliveryCounts} from '../web/modules/motion-cohort-delivery.js';

const rows = [
  {loaded:true, applies:true, decision:'accepted_with_exceptions', status:'needs_changes', notes:'仅呼吸待机；保留遮挡异常'},
  {loaded:true, applies:true, decision:'accepted', status:'stage_review'},
  {loaded:true, applies:false, decision:'accepted', status:'needs_changes', notes:'旧版通过'},
  {loaded:true, applies:true, decision:'rejected', status:'needs_changes'},
  {loaded:true, applies:true, decision:'revoked', status:'stage_review'},
  {loaded:false, applies:true, decision:'accepted', notes:'不能显示未核实记录'},
];
const before = JSON.stringify(rows), counts = deliveryCounts(rows, 1);
assert.equal(rows.filter(r=>matchesVisual(r,'accepted')).length,2);
assert.equal(rows.filter(r=>matchesVisual(r,'exceptions')).length,1);
assert.equal(rows.filter(r=>matchesVisual(r,'pending')).length,3);
assert.equal(rows.filter(r=>matchesVisual(r,'rejected')).length,1);
assert.equal(visualState({}),'pending'); // Missing candidates remain unreviewed.
assert.equal(matchesVisual({},'accepted'),false);
assert.equal(visualNotes(rows[0]),'验收说明：仅呼吸待机；保留遮挡异常');
assert.equal(visualNotes(rows[2]),'历史说明（不适用于当前证据）：旧版通过');
assert.equal(visualNotes(rows[5]),'');
assert.equal(visualNotes({loaded:true, notes:{}}),'');
assert.equal(visualNotes({loaded:true, notes:'  '}),'');
assert.deepEqual(deliveryCounts(rows,1),counts);
assert.equal(counts.technical_changes,3); // Visual acceptance must not clear failures.
assert.equal(Object.values(counts).reduce((a,b)=>a+b),7);
assert.equal(JSON.stringify(rows),before);
console.log('Passed: visual scope, stale/revoked/unread decisions, missing rows, immutable technical denominator');
