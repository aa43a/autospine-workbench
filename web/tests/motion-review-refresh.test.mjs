import test from 'node:test';
import assert from 'node:assert/strict';
import {fixture} from './motion-support-fixture.mjs';
import {collectSupportSnapshot} from '../modules/motion-support-snapshot.js';
import {matchingReviewRows,applyReviewRefresh} from '../../tools/m4_review_refresh_helpers.mjs';

async function setup(){
  const f=fixture(),parent=f.addAlternative(),registration=f.addRelated(parent);
  const snapshot=await collectSupportSnapshot(f.pack,f.get);
  const matches=matchingReviewRows(snapshot,parent,registration);
  const review=structuredClone(matches[0].review);
  review.revision++;review.current.revision++;review.current.notes='new explicit decision';
  return {snapshot,matches,review,parent,registration};
}
test('nested registration refresh leaves baseline and parent review unchanged',async()=>{
  const s=await setup(),before=JSON.stringify(s.snapshot.rows[0].review);
  const parentBefore=JSON.stringify(s.snapshot.rows[0].alternatives.rows[0].review);
  applyReviewRefresh(s.matches,s.review,s.parent,s.registration,'now');
  assert.equal(s.matches[0].review.revision,2);
  assert.equal(s.matches[0].review_checked_at,'now');
  assert.equal(JSON.stringify(s.snapshot.rows[0].review),before);
  assert.equal(JSON.stringify(s.snapshot.rows[0].alternatives.rows[0].review),parentBefore);
  assert.equal(matchingReviewRows(s.snapshot,s.parent,null).length,1);
});
test('evidence drift, wrong registration and version rollback fail before any mutation',async()=>{
  for(const change of [r=>r.evidence_sha256='changed',r=>r.readiness.status='stage_review',
    r=>r.registration_sha256='wrong',r=>r.current.registration_sha256='wrong',
    r=>r.revision=0,r=>r.current.production_authorized=true]){
    const s=await setup(),second=structuredClone(s.matches[0]);s.matches.push(second);
    const before=JSON.stringify(s.matches);change(s.review);
    assert.throws(()=>applyReviewRefresh(s.matches,s.review,s.parent,s.registration,'now'),/evidence_changed/);
    assert.equal(JSON.stringify(s.matches),before);
  }
});
test('a later mismatching duplicate does not partially update an earlier match',async()=>{
  const s=await setup(),second=structuredClone(s.matches[0]);second.review.evidence_sha256='other';
  s.matches.push(second);const before=JSON.stringify(s.matches);
  assert.throws(()=>applyReviewRefresh(s.matches,s.review,s.parent,s.registration,'now'),/evidence_changed/);
  assert.equal(JSON.stringify(s.matches),before);
});
