import test from 'node:test';
import assert from 'node:assert/strict';
import { loadAssetProgress, progressRows } from '../modules/asset-progress.js';
const fulfilled = value => ({ status: 'fulfilled', value });
const rows = job => progressRows([fulfilled({ choice: 'ordinary' }), fulfilled({ source_registered: true }),
  fulfilled({ status: 'ready', can_build: true }), fulfilled({ job })]);

test('persisted blocked and withdrawn sleeve results cannot appear accepted', () => {
  assert.match(rows({ status: 'blocked', result: { records: [{ status: 'blocked', reason_code: 'geometry_failure' }] } })[3].text, /1 个区域.*geometry_failure/);
  assert.match(rows({ status: 'needs_review' })[3].text, /不代表视觉验收或正式采用/);
  assert.match(rows({ status: 'needs_review', candidate_withdrawn: true })[3].text, /已撤回/);
  assert.match(rows({ status: 'failed', reason_code: 'sleeve_job_interrupted' })[3].text, /sleeve_job_interrupted/);
  assert.match(rows(null)[3].text, /旧来源结果不作为当前完成证据/);
});
test('partial reads fail independently and mismatched project evidence is rejected', async () => {
  const calls = [];
  const result = await loadAssetProgress('new asset', async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => ({ project_id: url.endsWith('/route') ? 'other' : 'new asset', authority: 'none', source_registered: true }) };
  });
  assert.equal(calls.length, 4); assert.ok(calls.every(c => c.url.includes('/new%20asset/') && c.options.cache === 'no-store'));
  assert.match(result[0].text, /读取失败/); assert.match(result[1].text, /已登记/);
  assert.match(rows({ status: 'running', step: 'repair: running' })[3].text, /自动修正/);
});
