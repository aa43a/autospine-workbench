import test from 'node:test';
import assert from 'node:assert/strict';
import {independentAcceptance,independentAcceptedEntries} from '../modules/motion-support-acceptance.js';
import {supportReportHTML} from '../modules/motion-support-report.js';
import {fixture} from './motion-support-fixture.mjs';
import {collectSupportSnapshot} from '../modules/motion-support-snapshot.js';
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
test('nested accepted links retain exact parent, registration and detail anchor',()=>{
  const view={...accepted(),related:family([accepted('view','registration')])};
  const entries=independentAcceptedEntries(snapshot({alternatives:family([view]),policy_variants:family([view])}));
  assert.equal(entries.length,2);
  assert.deepEqual(entries[1],{cell:0,anchor:'cell-0-alternatives-0-related-0',
    job_id:'view',artifact_sha256:'artifact',registration_sha256:'registration'});
  const conflict=structuredClone(view);conflict.related.rows[0].review.current.decision='revoked';
  assert.equal(independentAcceptedEntries(snapshot({alternatives:family([view]),policy_variants:family([conflict])})).length,1);
});
test('report exposes accepted independent player and matching anomaly anchor in summary table',async()=>{
  const f=fixture();f.addRelated();
  const data=await collectSupportSnapshot(f.pack,f.get);
  const html=supportReportHTML(data,'http://127.0.0.1:8918/ignored-path');
  const table=html.slice(html.indexOf('<table>'),html.indexOf('</table>'));
  const row=data.rows[0],child=row.related.rows[0];
  assert.ok(table.includes(`http://127.0.0.1:8918/api/motions/${row.job_id}/view/related-candidates/${child.registration_sha256}/player.html`));
  assert.ok(table.includes('href="#cell-0-related-0"'));
  assert.ok(html.includes('id="cell-0-related-0"'));
  assert.ok(table.includes('固定候选交付状态'));
});
