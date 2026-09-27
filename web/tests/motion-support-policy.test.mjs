import assert from 'node:assert/strict';
import {test} from 'node:test';
import {fixture} from './motion-support-fixture.mjs';
import {collectSupportSnapshot} from '../modules/motion-support-snapshot.js';
import {supportTotals,supportReportHTML} from '../modules/motion-support-report.js';

test('policy acceptance and technical failures remain independent of baseline totals',async()=>{
  const f=fixture(),id=f.addAlternative();
  const view=f.registry.get(`/api/motions/${f.targetId}/compare-targets`);
  const policy=structuredClone(view);
  policy.profile='motion-policy-variant-inventory-v1';policy.recommended_job_id=null;
  policy.rows=policy.rows.filter(r=>r.job_id===id);
  policy.matching_candidates=policy.rows.length;
  policy.rows[0].policy_changes={contact_correction:{baseline:true,candidate:false}};
  f.registry.set(`/api/motions/${f.targetId}/policy-variants`,policy);
  view.rows=view.rows.filter(r=>r.job_id!==id);view.matching_candidates=view.rows.length;
  const snapshot=await collectSupportSnapshot(f.pack,f.get);
  assert.equal(snapshot.rows[0].policy_variants.rows[0].job_id,id);
  assert.equal(snapshot.rows[0].policy_variants.complete,true);
  assert.equal(supportTotals(snapshot).accepted,1);
  assert.ok(snapshot.exception_index.some(r=>r.family==='不同策略候选'&&r.kind==='technical'));
  const html=supportReportHTML(snapshot,'http://127.0.0.1:8918');
  assert.ok(html.includes('cell-0-policy_variants-0'));
  assert.ok(html.includes('不参与视角推荐'));
});

test('missing and truncated policy inventories remain explicitly incomplete',async()=>{
  const f=fixture();
  const missing=await collectSupportSnapshot(f.pack,f.get);
  assert.equal(supportTotals(missing).policies_checked,0);
  assert.ok(missing.exception_index.some(r=>r.family==='不同策略候选'&&r.stage==='候选清单'));
  const policy=structuredClone(f.registry.get(`/api/motions/${f.targetId}/compare-targets`));
  policy.profile='motion-policy-variant-inventory-v1';policy.recommended_job_id=null;
  policy.rows=[];policy.matching_candidates=26;policy.complete=false;
  f.registry.set(`/api/motions/${f.targetId}/policy-variants`,policy);
  const partial=await collectSupportSnapshot(f.pack,f.get);
  assert.equal(partial.rows[0].policy_variants.status,'verified');
  assert.equal(partial.rows[0].policy_variants.complete,false);
  assert.equal(supportTotals(partial).policies_checked,0);
  assert.equal(supportTotals(partial).accepted,supportTotals(missing).accepted);
});
