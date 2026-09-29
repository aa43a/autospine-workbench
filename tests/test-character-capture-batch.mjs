import test from 'node:test';
import assert from 'node:assert/strict';
import {captureBatch,CAPTURE_BATCH_SIZE} from '../tools/character-capture-batch.mjs';

test('batches preserve every independent frame and capture the matching framebuffer',()=>{
  const calls=[]; let active;
  globalThis.window={captureFrame(animation,index){calls.push(index);active=index;return {animation,index};},
    framePNG(){return `png-${active}`;}};
  try {
    const rows=[];
    for(let start=0;start<19;start+=CAPTURE_BATCH_SIZE)rows.push(...captureBatch({animation:'walk',start,
      end:Math.min(19,start+CAPTURE_BATCH_SIZE),screenshotIndices:[0,7,8,18]}));
    assert.deepEqual(calls,Array.from({length:19},(_,i)=>i));
    assert.deepEqual(rows.filter(r=>r.png).map(r=>[r.result.index,r.png]),[[0,'png-0'],[7,'png-7'],[8,'png-8'],[18,'png-18']]);
    assert.ok(rows.every(r=>r.result.animation==='walk'));
  } finally {delete globalThis.window;}
});

test('a failed intermediate official frame aborts the batch instead of skipping it',()=>{
  const calls=[];
  globalThis.window={captureFrame(animation,index){calls.push(index);if(index===4)throw Error('official_pose_mismatch');return {animation,index};},
    framePNG(){throw Error('unexpected screenshot');}};
  try {
    assert.throws(()=>captureBatch({animation:'wave',start:2,end:8,screenshotIndices:[]}),/official_pose_mismatch/);
    assert.deepEqual(calls,[2,3,4]);
  } finally {delete globalThis.window;}
});
