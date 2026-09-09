import test from 'node:test';
import assert from 'node:assert/strict';
import {sleeveImageFrame} from './modules/sleeve-region-review.js';

test('nonzero layer offsets use right-minus-left and bottom-minus-top', () => {
  assert.deepEqual(sleeveImageFrame([269,217,589,988]),
    {x:269,y:217,width:320,height:771,viewBox:'259 207 340 791'});
  assert.deepEqual(sleeveImageFrame([346,257,584,669]),
    {x:346,y:257,width:238,height:412,viewBox:'336 247 258 432'});
  const a=sleeveImageFrame([-20,-30,80,170]);
  assert.equal(a.width,100); assert.equal(a.height,200);
});

test('invalid or degenerate extents fail instead of distorting source image', () => {
  for (const box of [[0,0,0,10],[0,0,10,0],[0,0,NaN,10],[0,0,Infinity,10],[1,2,3],null])
    assert.throws(() => sleeveImageFrame(box));
});
