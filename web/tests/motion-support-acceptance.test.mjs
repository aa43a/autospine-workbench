import test from 'node:test';
import assert from 'node:assert/strict';
import {independentAcceptance} from '../modules/motion-support-acceptance.js';
const accepted=(job='view',registration)=>({job_id:job,artifact_sha256:'artifact',
  registration_sha256:registration,status:'verified',review:{current_applies:true,
    revision:1,evidence_sha256:'evidence',current:{decision:'accepted_with_exceptions'}}});
const family=rows=>({status:'verified',complete:true,rows});
const snapshot=extra=>({rows:[{job_id:'fixed',artifact_sha256:'fixed-artifact',
  status:'verified',...extra}]});
test('deduplicates alternative and policy routes including nested related acceptance',()=>{
  const view={...accepted(),related:family([accepted('view','registration')])};
  assert.deepEqual(independentAcceptance(snapshot({alternatives:family([view]),
    policy_variants:family([structuredClone(view)])})),{accepted:2,conflicting:0});
});
test('stale, revoked, failed reads and imported local feedback are not acceptance',()=>{
  const stale=accepted('stale');stale.review.current_applies=false;
  const revoked=accepted('revoked');revoked.review.current.decision='revoked';
  const failed=accepted('failed');failed.status='unavailable';
  const local={...accepted('local'),review:{imported_visual:{decision:'accepted'}}};
  assert.equal(independentAcceptance(snapshot({alternatives:family([stale,revoked,failed,local])})).accepted,0);
});
test('conflicting repeated reads do not count as acceptance',()=>{
  const first=accepted(),second=accepted();second.review.revision=2;
  assert.deepEqual(independentAcceptance(snapshot({alternatives:family([first]),
    policy_variants:family([second])})),{accepted:0,conflicting:1});
});
test('partial inventory still counts verified entries, but unavailable families do not',()=>{
  const partial={...family([accepted()]),complete:false};
  assert.equal(independentAcceptance(snapshot({alternatives:partial})).accepted,1);
  assert.equal(independentAcceptance(snapshot({alternatives:{...partial,status:'unavailable'}})).accepted,0);
});
test('fixed candidate never becomes an independent acceptance',()=>{
  const row={...accepted('fixed'),artifact_sha256:'fixed-artifact'};
  assert.equal(independentAcceptance(snapshot({alternatives:family([row])})).accepted,0);
});
