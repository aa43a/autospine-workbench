import assert from 'node:assert/strict';
import {test} from 'node:test';
import {collectSupportSnapshot} from '../modules/motion-support-snapshot.js';
import {supportExceptions} from '../modules/motion-support-exceptions.js';
import {supportReportHTML, supportTotals} from '../modules/motion-support-report.js';
import {fixture} from './motion-support-fixture.mjs';
const collect = f => collectSupportSnapshot(f.pack, f.get);

test('accepted baseline keeps technical failures, independent candidates retain their own review', async () => {
  const f = fixture(), reg = f.addRelated(), alt = f.addAlternative();
  const state = f.registry.get(`/api/motions/${alt}/stage-review`);
  state.current = null; state.revision = 0; state.current_applies = false;
  const snapshot = await collect(f), before = JSON.stringify(snapshot), totals = supportTotals(snapshot);
  const rows = supportExceptions(snapshot);
  assert.deepEqual(snapshot.exception_index, rows);
  assert.equal(rows.filter(r => r.kind === 'technical').length, 3);
  assert.equal(rows.filter(r => r.kind === 'visual').length, 1);
  assert.equal(rows.find(r => r.kind === 'visual').job_id, alt);
  assert.equal(rows.find(r => r.family === '独立改进').registration_sha256, reg);
  assert.equal(rows.find(r => r.stage === '候选').anchor, null);
  assert.equal(JSON.stringify(snapshot), before);
  assert.deepEqual(supportTotals(snapshot), totals);
  const html = supportReportHTML(snapshot, 'http://127.0.0.1:8918');
  for (const row of rows.filter(r => r.anchor)) assert.ok(html.includes(`id="${row.anchor}"`));
});

test('missing stages, failed inventory and stale conclusions are explicit rather than passed', async () => {
  const f = fixture(), r = f.registry.get(`/api/motions/${f.targetId}/stage-review`);
  r.readiness.stages = r.readiness.stages.filter(s => s.stage !== 'Runtime');
  r.current_applies = false;
  f.registry.delete(`/api/motions/${f.targetId}/compare-targets`);
  const rows = supportExceptions(await collect(f));
  assert.ok(rows.some(r => r.stage === 'Runtime' && r.kind === 'evidence'));
  assert.ok(rows.some(r => r.family === '替代视角' && r.stage === '候选清单'));
  assert.ok(rows.some(r => r.kind === 'visual' && r.reason.includes('历史结论')));
});

test('queue escapes diagnostic text and includes failures beyond the five standard gates', async () => {
  const f = fixture(), r = f.registry.get(`/api/motions/${f.targetId}/stage-review`);
  r.readiness.stages.push({stage:'裙腿',status:'needs_changes',explanation:'<img src=x onerror=alert(1)> & 覆盖不足'});
  const snapshot = await collect(f), rows = supportExceptions(snapshot);
  assert.ok(rows.some(r => r.stage === '裙腿' && r.kind === 'technical'));
  const html = supportReportHTML(snapshot,'http://127.0.0.1:8918');
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.doesNotMatch(html, /<img src=x/);
});
