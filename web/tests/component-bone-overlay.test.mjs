import test from 'node:test';
import assert from 'node:assert/strict';
import { toggleComponentBone } from '../modules/component-bone-overlay.js';
test('canvas bone clicks toggle without mutating input and enforce four-bone limit', () => {
  const ids=['a','b','c','d'], chosen=['a'];
  assert.deepEqual(toggleComponentBone(chosen,'b',ids),['a','b']); assert.deepEqual(chosen,['a']);
  assert.deepEqual(toggleComponentBone(chosen,'a',ids),[]);
  assert.throws(()=>toggleComponentBone(ids,'e',[...ids,'e']));
  assert.throws(()=>toggleComponentBone([],'foreign',ids));
});
