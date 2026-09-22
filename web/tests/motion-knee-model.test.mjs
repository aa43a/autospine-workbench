import test from 'node:test';
import assert from 'node:assert/strict';
import {kneeRows,strongestKnee} from '../modules/motion-knee-model.js';
function report(){return {artifact_sha256:'exact',profile:'knee-projection-observation-v1',rows:[0,1].flatMap(time=>['left','right'].map(side=>({
  time,side,status:'projected_side_consistent',source:{status:'measured',bend_degrees:70,projection_visibility:[time ? .35 : 1,.8],screen_plane_alignment:.1}})))};}
test('strong shortening is actionable even when screen bend side agrees',()=>{
  const rows=kneeRows(report(),'exact').filter(r=>r.side==='left');assert.equal(strongestKnee(rows),1);
  assert.equal(rows[1].issues.length,1);assert.equal(rows[1].status,'projected_side_consistent');
});
test('old source report without plane data remains readable',()=>{
  const r=report();for(const row of r.rows)delete row.source.screen_plane_alignment;assert.equal(kneeRows(r,'exact').length,4);
});
test('reject stale identity, missing side, duplicate time and nonfinite measurements',()=>{
  assert.throws(()=>kneeRows(report(),'stale'));
  const r=report();r.rows=r.rows.filter(r=>r.side==='left');assert.throws(()=>kneeRows(r,'exact'));
  const duplicate=report();duplicate.rows.push(duplicate.rows[0]);assert.throws(()=>kneeRows(duplicate,'exact'));
  const nan=report();nan.rows[0].source.projection_visibility[0]=NaN;assert.throws(()=>kneeRows(nan,'exact'));
});
