import test from 'node:test';
import assert from 'node:assert/strict';
import {geometryLines} from '../modules/motion-repair-geometry.js';
const row={slot:'arm',animation:'move',attachment:'original',passed:true,
  min_area_ratio:1,max_edge_stretch:1,inversion_samples:0,sample_count:80};

test('passing original never hides failed switched attachment',()=>{
  const records=[row,{...row,attachment:'bent',passed:false,min_area_ratio:-.2,inversion_samples:3,sample_count:20}];
  const lines=geometryLines('修正候选',{records},'arm');
  assert.equal(lines.length,2);assert.match(lines[0],/original.*限定采样通过/);
  assert.match(lines[1],/bent.*需处理/);assert.match(lines[1],/翻转采样 3/);
});

test('all animations remain distinct, unrelated slots excluded',()=>{
  const records=[row,{...row,animation:'other',passed:false},{...row,slot:'leg'}];
  const lines=geometryLines('原候选',{records},'arm');
  assert.equal(lines.length,2);assert.match(lines[1],/other.*需处理/);
});

test('missing baseline is unavailable, not passing or zero failures',()=>{
  assert.deepEqual(geometryLines('原候选',null,'arm'),['原候选：缺少附件检查记录。']);
  assert.match(geometryLines('原候选',{records:[{...row,passed:undefined,attachment:undefined}]},'arm')[0],/状态未提供/);
});
