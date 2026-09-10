import test from 'node:test';
import assert from 'node:assert/strict';
import { createWorkbenchSleeveAnnotation, readSleeveAnnotation, annotationReason, annotationMigrationText } from '../modules/workbench-sleeve-annotation.js';
const context = () => ({ projectId: 'alice', resolvedSha: 'a'.repeat(64) });
const response = () => ({ project_id: 'alice', source_sha256: 'a'.repeat(64), revision: 0, status: 'ready', can_build: false,
  candidate_sha256: 'b'.repeat(64), review_url: '/api/projects/alice/automation/sleeves/annotation/view', authority: 'none' });
const tick = () => new Promise(resolve => setImmediate(resolve));
test('annotation rejects external and cross-project review URLs', () => {
  readSleeveAnnotation(response(), context());
  for (const review_url of ['https://example.com', '/api/projects/other/automation/sleeves/annotation/view', '//evil/review'])
    assert.throws(() => readSleeveAnnotation({ ...response(), review_url }, context()));
});
test('annotation migration remains unsaved and reports retained roles without adoption', async () => {
  const migration = { manual_count: 12, geometry_count: 4, pending_count: 3, authority: 'none', requires_save: true };
  let model;
  const ui = createWorkbenchSleeveAnnotation(null, { context, apiRequest: async () => ({ ...response(), migration }) },
    { view: { element: {}, render: value => { model = value; } } });
  ui.sync({ preparationEditable: true }); await tick();
  assert.match(model.migrationMessage, /人工标注 12.*几何预填 4.*待处理 3/);
  assert.match(model.migrationMessage, /新版本尚未保存.*再次保存.*不代表自动采用/);
  assert.doesNotMatch(model.message, /草稿已保存/);
  assert.equal(annotationMigrationText(undefined), '');
  for (const patch of [{ manual_count: -1 }, { geometry_count: 0.5 }, { pending_count: NaN }, { authority: 'approved' }, { requires_save: false }])
    assert.throws(() => readSleeveAnnotation({ ...response(), migration: { ...migration, ...patch } }, context()), /迁移摘要/);
});
test('annotation preparation preserves current source and refuses unsaved edits', async () => {
  const c = context(), requests = []; let model;
  const ui = createWorkbenchSleeveAnnotation(null, { context: () => c, apiRequest: async (url, options) => { requests.push([url, options]); return response(); } },
    { view: { element: {}, render: value => { model = value; } } });
  ui.sync({ preparationEditable: true }); await tick(); assert.equal(model.reviewUrl, response().review_url);
  c.dirty = true; ui.sync({ preparationEditable: true }); await ui.prepare(); assert.equal(requests.length, 1); assert.equal(model.reviewUrl, null);
  c.dirty = false; await ui.prepare(); assert.equal(requests.length, 2);
  assert.match(requests[1][0], /annotation\/prepare$/); assert.deepEqual(JSON.parse(requests[1][1].body), { expected_resolved_sha256: c.resolvedSha });
  assert.match(annotationReason('animated_source_missing'), /来源准备.*关节复核/);
});
