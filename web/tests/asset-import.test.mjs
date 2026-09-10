import test from 'node:test';
import assert from 'node:assert/strict';
import { validatePsdFile, readImportJob, importJobMessage, createAssetImport } from '../modules/asset-import.js';
const job_id = `import-${'a'.repeat(32)}`;
test('PSD intake rejects empty, oversized and non-PSD input', () => {
  assert.throws(() => validatePsdFile({ name: 'a.png', size: 1 }));
  assert.throws(() => validatePsdFile({ name: 'a.psd', size: 0 }));
  assert.throws(() => validatePsdFile({ name: 'a.psd', size: 256 * 1024 * 1024 + 1 }));
  validatePsdFile({ name: '角色.PSD', size: 256 * 1024 * 1024 });
});
test('successful import refreshes assets once and stops polling after terminal response', async () => {
  class Element extends EventTarget {
    constructor(tag) { super(); this.tagName = tag; this.children = []; this.classList = { add() {}, remove() {} }; }
    append(...nodes) { this.children.push(...nodes); }
    setAttribute() {} removeAttribute() {}
  }
  const root = new Element('section');
  const doc = { getElementById: () => root, createElement: tag => new Element(tag) };
  let scheduled, refreshed = 0, stored = null;
  const importUi = createAssetImport(doc, {
    upload: async () => ({ job_id, status: 'running', step: 'parsing' }),
    request: async () => ({ ok: true, json: async () => ({ job_id, status: 'succeeded', step: 'complete', project_id: 'new-character' }) }),
    schedule: fn => { scheduled = fn; return 1; }, unschedule: () => { scheduled = null; },
    storage: { getItem: () => stored, setItem: (_, value) => { stored = value; }, removeItem: () => { stored = null; } },
    onComplete: () => refreshed++,
  });
  await importUi.start({ name: 'new.psd', size: 42 });
  assert.equal(stored, job_id); assert.equal(typeof scheduled, 'function');
  await scheduled();
  assert.equal(scheduled, null); assert.equal(stored, null); assert.equal(refreshed, 1);
  const link = root.children.find(el => el.tagName === 'div').children.find(el => el.tagName === 'a');
  assert.equal(link.href, '/?project=new-character'); assert.equal(link.hidden, false);
});
test('import terminal success requires project identity and parser status does not invent percent', () => {
  assert.throws(() => readImportJob({ job_id, status: 'succeeded', step: 'complete' }));
  const job = readImportJob({ job_id, status: 'running', step: 'parsing' });
  assert.match(importJobMessage(job), /解析/);
  assert.doesNotMatch(importJobMessage(job), /%/);
  assert.throws(() => readImportJob({ ...job, job_id: '../escape' }));
});
test('backend PSD limitations have actionable Chinese explanations and duplicates are not claimed new', () => {
  for (const reason_code of ['psd_color_mode_unsupported', 'psd_layer_kind_unsupported', 'psd_decoder_unavailable', 'psd_queue_full', 'psd_import_interrupted']) {
    assert.doesNotMatch(importJobMessage({ status: 'failed', reason_code }), /导入失败（/);
  }
  assert.match(importJobMessage({ status: 'failed', reason_code: 'psd_color_mode_unsupported' }), /RGB、8 位/);
  assert.match(importJobMessage({ status: 'succeeded' }), /复用已有项目/);
  assert.doesNotMatch(importJobMessage({ status: 'succeeded' }), /已创建/);
});
