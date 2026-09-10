import test from 'node:test';
import assert from 'node:assert/strict';
import { createSleeveDraftSave } from '../modules/sleeve-region-review.js';

test('project save uses isolated snapshot, prevents duplicate submits and detects edits made during save', async () => {
  let draft = { records: [{ role: 'hand' }] }, complete, received, calls = 0;
  const button = {}, message = {};
  const save = createSleeveDraftSave(button, message, () => draft, snapshot => {
    received = snapshot; calls++; return new Promise(resolve => { complete = resolve; });
  });
  const pending = save(); assert.equal(button.disabled, true);
  await save(); assert.equal(calls, 1);
  draft.records[0].role = 'cuff'; assert.equal(received.records[0].role, 'hand');
  complete(); await pending;
  assert.equal(button.disabled, false); assert.match(message.textContent, /又有修改.*再次保存/);
});
test('failed save retains draft and allows retry, success reports saved snapshot', async () => {
  const draft = { records: [] }, button = {}, message = {}; let fail = true;
  const save = createSleeveDraftSave(button, message, () => draft, async () => { if (fail) throw Error('来源已变化'); });
  await save(); assert.match(message.textContent, /保存失败.*来源已变化.*仍保留/); assert.equal(button.disabled, false);
  fail = false; await save(); assert.match(message.textContent, /标注已保存到项目/); assert.deepEqual(draft, { records: [] });
});
