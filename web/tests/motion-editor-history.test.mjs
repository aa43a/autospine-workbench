import test from 'node:test';
import assert from 'node:assert/strict';
import {createEditHistory} from '../modules/motion-editor-history.js';
test('undo and redo preserve independent drafts and discard abandoned redo branches',()=>{
  const h=createEditHistory(),a={keys:[{time:0,yaw:0}]},b={keys:[{time:0,yaw:360}]};
  h.record(a);a.keys[0].yaw=90;
  assert.deepEqual(h.undo(b),{keys:[{time:0,yaw:0}]});
  assert.deepEqual(h.redo(a),b);
  h.undo(b);h.record(a);assert.equal(h.canRedo,false);
  h.reset();assert.equal(h.canUndo,false);assert.equal(h.undo(b),null);
});
test('history is bounded',()=>{
  const h=createEditHistory(2);h.record(1);h.record(2);h.record(3);
  assert.equal(h.undo(4),3);assert.equal(h.undo(3),2);assert.equal(h.undo(2),null);
});
