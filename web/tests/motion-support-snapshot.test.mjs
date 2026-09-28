import assert from 'node:assert/strict';
import {test} from 'node:test';
import {collectSupportSnapshot,validatePack} from '../modules/motion-support-snapshot.js';
import {supportTotals,supportReportHTML} from '../modules/motion-support-report.js';
import {fixture,hash,job} from './motion-support-fixture.mjs';
const collect=f=>collectSupportSnapshot(f.pack,f.get,{now:()=> '2026-09-26T00:00:00Z'});

test('repairs registered under an alternative are included without changing baseline totals',async()=>{
  const f=fixture(),parent=f.addAlternative(),registration=f.addRelated(parent);
  const s=await collect(f),nested=s.rows[0].alternatives.rows[0].related;
  assert.equal(nested.status,'verified');assert.equal(nested.complete,true);
  assert.equal(nested.rows[0].registration_sha256,registration);
  assert.equal(supportTotals(s).accepted,1);
  const html=supportReportHTML(s,'http://127.0.0.1:8918');
  assert.ok(html.includes(`/api/motions/${parent}/view/related-candidates/${registration}/player.html`));
  assert.ok(s.exception_index.some(e=>e.job_id===parent&&e.registration_sha256===registration&&e.stage==='遮挡'));
  f.registry.delete(`/api/motions/${parent}/view/related-candidates.json`);
  const missing=await collect(f);
  assert.equal(missing.rows[0].alternatives.complete,false);
  assert.equal(supportTotals(missing).accepted,1);
});

test('full inventory retains failures, missing items, human scope and independent candidates',async()=>{
  const f=fixture();f.addAlternative();f.addRelated();const before=JSON.stringify([...f.registry]);
  const s=await collect(f),t=supportTotals(s);
  assert.equal(s.rows[0].status,'verified');assert.equal(s.rows[0].related.rows.length,1);
  assert.equal(s.rows[0].alternatives.rows.length,1);assert.equal(s.missing.length,1);
  assert.equal(t.accepted,1);assert.equal(t.delivery.technical_changes,1);assert.equal(t.delivery.missing,1);
  assert.deepEqual(t.gates['遮挡'],{sampled_pass:0,needs_changes:1,unmeasured:1});
  assert.deepEqual(t.gates.Runtime,{sampled_pass:1,needs_changes:0,unmeasured:1});
  assert.equal(s.rows[0].review.current.notes,'呼吸阶段可接受，保留技术异常');
  assert.equal(s.rows[0].source_link.source_end,4);
  assert.equal(s.authority,'none');assert.equal(s.production_authorized,false);
  assert.equal(JSON.stringify([...f.registry]),before);
  assert.equal(f.calls.filter(p=>p===`/api/motions/${f.sourceId}`).length,1);
});

test('failed source relationship keeps row unknown and never reads visual acceptance',async()=>{
  const f=fixture();f.registry.get(`/api/motions/${f.targetId}/view/source-link.json`).source_job_id=job('4');
  const s=await collect(f);assert.equal(s.rows[0].status,'unavailable');assert.equal(supportTotals(s).accepted,0);
  assert.equal(f.calls.some(p=>p.endsWith('/stage-review')),false);
  assert.equal(supportTotals(s).gates.Runtime.unmeasured,2);
});

test('current evidence mismatch is not acceptance; known compatible extension remains explicit',async()=>{
  const f=fixture(),r=f.registry.get(`/api/motions/${f.targetId}/stage-review`);r.current.evidence_sha256=hash('e');
  assert.equal((await collect(f)).rows[0].status,'unavailable');
  r.current_applies=false;r.evidence_match='evidence_changed';
  const stale=await collect(f);assert.equal(stale.rows[0].status,'verified');assert.equal(supportTotals(stale).accepted,0);
  r.current_applies=true;r.evidence_match='legacy_empty_projection_fields';
  const compatible=await collect(f);assert.equal(supportTotals(compatible).accepted,1);
  assert.equal(compatible.rows[0].review.evidence_match,'legacy_empty_projection_fields');
});

test('alternative evidence races and partial inventories stay independent of baseline',async()=>{
  const f=fixture(),alt=f.addAlternative();
  f.registry.get(`/api/motions/${alt}/stage-review`).evidence_sha256=hash('6');
  f.registry.get(`/api/motions/${alt}/stage-review`).current_applies=false;
  const s=await collect(f);assert.equal(s.rows[0].alternatives.rows[0].status,'unavailable');
  assert.equal(supportTotals(s).accepted,1);assert.equal(supportTotals(s).alternatives_checked,0);
  const cmp=f.registry.get(`/api/motions/${f.targetId}/compare-targets`);cmp.complete=false;cmp.matching_candidates=28;
  const partial=await collect(f);assert.equal(partial.rows[0].alternatives.inventory_complete,false);
  assert.match(supportReportHTML(partial,'http://127.0.0.1:8918'),/清单或证据不完整/);
});

test('related revisions and registration mismatches cannot inherit baseline review',async()=>{
  const f=fixture(),reg=f.addRelated(),state=f.registry.get(`/api/motions/${f.targetId}/related-candidates/${reg}/stage-review`);
  state.revision=2;state.current.revision=2;
  let s=await collect(f);assert.equal(s.rows[0].related.rows[0].status,'unavailable');
  assert.equal(supportTotals(s).related_checked,0);assert.equal(supportTotals(s).accepted,1);
  state.registration_sha256=hash('f');s=await collect(f);
  assert.match(s.rows[0].related.rows[0].reason,/关联检查身份/);
});

test('cancel aborts collection and cannot produce a partially complete report',async()=>{
  const f=fixture(),controller=new AbortController();
  await assert.rejects(()=>collectSupportSnapshot(f.pack,async path=>{controller.abort();return f.get(path);},{signal:controller.signal}),/停止/);
});

test('duplicated or forged cohort inventories rejected before network access',async()=>{
  const f=fixture();f.pack.groups[0].targets.push(f.pack.groups[0].targets[0]);
  assert.throws(()=>validatePack(f.pack));await assert.rejects(()=>collect(f));assert.equal(f.calls.length,0);
  const other=fixture();other.pack.coverage.expected=3;assert.throws(()=>validatePack(other.pack),/覆盖/);
});

test('all extra diagnostic stages, escaped human notes and full identities retained',async()=>{
  const f=fixture(),r=f.registry.get(`/api/motions/${f.targetId}/stage-review`);
  r.current.notes='<script>alert(1)</script> & 保留肩部异常';
  r.readiness.stages.push({stage:'肩部',status:'needs_changes',explanation:'顶点失败 12'});
  const s=await collect(f),html=supportReportHTML(s,'http://127.0.0.1:8918/path');
  assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>alert/);
  const clean=structuredClone(s);clean.rows[0].review.current.notes='safe note';
  const scripts=value=>[...value.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
  assert.equal(scripts(html).length,1); // Only the fixed local fragment-navigation helper.
  assert.deepEqual(scripts(html),scripts(supportReportHTML(clean,'http://127.0.0.1:8918/path')));
  assert.match(html,/肩部：需处理/);assert.match(html,new RegExp(f.asset));
  assert.match(html,/http:\/\/127.0.0.1:8918\/api\/motions\//);
  assert.throws(()=>supportReportHTML(s,'file:///tmp'),/地址无效/);
  assert.equal(supportTotals(s).delivery.technical_changes,1);
});

test('failed auxiliary lookup does not turn an existing baseline into an unverified one',async()=>{
  const f=fixture();f.registry.delete(`/api/motions/${f.targetId}/compare-targets`);
  const s=await collect(f);assert.equal(s.rows[0].status,'verified');assert.equal(s.rows[0].alternatives.status,'unavailable');
  assert.equal(supportTotals(s).verified,1);
});

test('aggregate success cannot hide an extra failure or a missing required gate',async()=>{
  const f=fixture(),r=f.registry.get(`/api/motions/${f.targetId}/stage-review`);
  r.readiness.status='stage_review';
  assert.equal(supportTotals(await collect(f)).delivery.technical_changes,1);
  r.readiness.stages=r.readiness.stages.filter(s=>s.stage!=='遮挡');
  assert.equal(supportTotals(await collect(f)).delivery.incomplete,1);
});

test('imported acceptance scope is visible until a later independent review supersedes it',async()=>{
  const f=fixture(),reg=f.addRelated(),state=f.registry.get(`/api/motions/${f.targetId}/related-candidates/${reg}/stage-review`);
  const current=structuredClone(state.current),entry=f.registry.get(`/api/motions/${f.targetId}/view/related-candidates.json`).rows[0];
  state.current=null;state.revision=0;state.current_applies=false;
  state.imported_visual={artifact_sha256:state.artifact_sha256,decision:'stage_accepted_with_retained_exceptions',
    user_response:'脚端阶段接受',scope:'仅脚端轨迹',retained_exceptions:['透明边缘仍异常'],technical_override:false,
    applies_to_other_candidates:false,production_authorized:false};
  entry.visual=structuredClone(state.imported_visual);entry.stage_review=structuredClone(state);
  let html=supportReportHTML(await collect(f),'http://127.0.0.1:8918');
  assert.match(html,/仅脚端轨迹/);assert.match(html,/透明边缘仍异常/);
  state.current={...current,decision:'revoked',notes:'撤销该独立候选接受'};state.revision=1;state.current_applies=true;
  entry.stage_review=structuredClone(state);
  const updated=await collect(f);html=supportReportHTML(updated,'http://127.0.0.1:8918');
  assert.match(html,/撤销该独立候选接受/);assert.doesNotMatch(html,/脚端阶段接受/);
  assert.equal(supportTotals(updated).accepted,1);
});
