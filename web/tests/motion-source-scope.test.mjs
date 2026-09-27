import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFile} from 'node:fs/promises';
import {sourceScope} from '../modules/motion-source-scope.js';

test('category descriptions apply only to the recorded fixed plan and source bytes',async()=>{
  const evidence=JSON.parse(await readFile(new URL('../../docs/benchmark/m4-source-category-observations-v1.json',import.meta.url),'utf8'));
  for(const r of evidence.records){
    const row={motion:r.motion_id,source_sha256:r.source_sha256};
    assert.equal(sourceScope(evidence.plan_sha256,row).authority,'none');
    assert.equal(sourceScope('0'.repeat(64),row),null);
    assert.equal(sourceScope(evidence.plan_sha256,{...row,source_sha256:'0'.repeat(64)}),null);
  }
  const r=evidence.records.find(r=>r.motion_id==='raise-arms');
  assert.match(sourceScope(evidence.plan_sha256,{motion:r.motion_id,source_sha256:r.source_sha256}).limits,/不是双臂/);
});
