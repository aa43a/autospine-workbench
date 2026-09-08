import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';
import assert from 'node:assert/strict';
vm.runInThisContext(await readFile(new URL('./limb-residual-metrics.js',import.meta.url),'utf8'));
const measure=globalThis.limbResidualMetrics;
test('unchanged and one-channel rounding are not marked changed',()=>{
  const r=measure([10,20,30,255],[11,20,30,255],1,1);
  assert.equal(r.changed_pixels,0);assert.equal(r.changed_rect_bottom_left,null);
  assert.equal(r.any_channel_changed_pixels,1);
});
test('same alpha color contribution differs from exposed transparency',()=>{
  const r=measure([100,100,100,255],[0,0,0,255],1,1);
  assert.equal(r.changed_pixels,1);assert.equal(r.alpha_changed_pixels,0);assert.equal(r.pixels_exposed_by_hiding,0);
});
test('alpha8 and bottom-left bounds are explicit',()=>{
  const full=new Uint8Array(16),without=new Uint8Array(16);full[15]=8;
  const r=measure(full,without,2,2);
  assert.equal(r.pixels_exposed_by_hiding,1);assert.deepEqual(r.changed_rect_bottom_left,[1,1,1,1]);
  full[15]=7;assert.equal(measure(full,without,2,2).pixels_exposed_by_hiding,0);
});
test('mismatched buffers fail',()=>assert.throws(()=>measure([0],[],1,1),/shape/));
