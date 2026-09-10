import test from 'node:test';
import assert from 'node:assert/strict';
import { filterAssets, assetMutation, assetTaskMessage, assetSourceMessage } from '../modules/asset-center.js';

test('asset filtering keeps archived and trashed projects separate while searching names and IDs', () => {
  const rows = [{ id: 'alice', name: '爱丽丝', lifecycle: 'active' }, { id: 'ALICE-2', name: '归档', lifecycle: 'archived' },
    { id: 'other', name: 'Alice', lifecycle: 'trashed' }];
  assert.deepEqual(filterAssets(rows, 'active', '爱丽'), [rows[0]]);
  assert.deepEqual(filterAssets(rows, 'archived', ' alice '), [rows[1]]);
  assert.deepEqual(filterAssets(rows, 'active', '归档'), []);
});
test('asset mutations preserve optimistic revision and distinguish trash from physical deletion', () => {
  assert.deepEqual(assetMutation({ revision: 7 }, 'trash'), { action: 'trash', expected_revision: 7 });
  assert.deepEqual(assetMutation({ revision: 8 }, 'rename', ' 灵梦 '), { action: 'rename', expected_revision: 8, name: '灵梦' });
  assert.throws(() => assetMutation({ revision: -1 }, 'restore'));
  assert.throws(() => assetMutation({ revision: 0 }, 'delete'));
  assert.throws(() => assetMutation({ revision: 0 }, 'rename', '  '));
});
test('active asset task has stage context without reporting stale completion or invented percentages', () => {
  assert.equal(assetTaskMessage({ kind: 'sleeves', status: 'running', step: 'repair: running' }), '袖装修复 · 正在自动修正与分支比较');
  assert.equal(assetTaskMessage({ kind: 'preparation', status: 'pending' }), '来源准备 · 已排队');
  assert.equal(assetTaskMessage({ kind: 'animation', status: 'running' }), '动画候选 · 正在处理');
  assert.equal(assetTaskMessage({ kind: 'sleeves', status: 'succeeded' }), null);
  assert.equal(assetTaskMessage(null), null);
  assert.doesNotMatch(assetTaskMessage({ kind: 'preview', status: 'running' }), /%/);
});
test('source filename is explicit upload metadata, not a renamed title or local path', () => {
  assert.equal(assetSourceMessage({ kind: 'uploaded_psd', file_names: ['原图.psd'] }), 'PSD 来源：原图.psd');
  assert.match(assetSourceMessage({ kind: 'audit', file_names: [] }), /未登记上传 PSD/);
  assert.match(assetSourceMessage(undefined), /不可核实/);
  assert.doesNotMatch(assetSourceMessage({ kind: 'uploaded_psd', file_names: ['E:\\secret\\source.psd'] }), /secret/);
});
