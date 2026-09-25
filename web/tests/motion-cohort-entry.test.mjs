import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {navigationPack} from '../modules/motion-cohort-entry.js';
const calls=[];
const get=async path=>{calls.push(path);return {fixed:true};};
assert.deepEqual(await navigationPack('','?pack=m4-fixed',get),{fixed:true});
assert.deepEqual(calls,['/m4-fixed-cohort.json']);
assert.deepEqual(await navigationPack('#'+encodeURIComponent('{"version":1}'),'?pack=m4-fixed',get),{version:1});
assert.equal(calls.length,1);
await assert.rejects(navigationPack('','?pack=https://example.com/data',get),/未选择/);
await assert.rejects(navigationPack('#'+'x'.repeat(100000),'',get),/过大/);
const pack=JSON.parse(await readFile(new URL('../m4-fixed-cohort.json',import.meta.url),'utf8'));
assert.equal(pack.groups.length,8);
assert.deepEqual(pack.coverage,{expected:24,available:24,missing:[]});
const jobs=new Set();
for(const g of pack.groups){
  assert.match(g.job_id,/^motion-[a-f0-9]{32}$/);assert.match(g.source_sha256,/^[a-f0-9]{64}$/);
  assert.deepEqual(g.targets.map(t=>t.label).sort(),['alice','hongmeiling','huiye']);
  for(const t of g.targets){assert.match(t.job_id,/^motion-[a-f0-9]{32}$/);assert.match(t.artifact_sha256,/^[a-f0-9]{64}$/);jobs.add(t.job_id);}
}
assert.equal(jobs.size,24);
assert.equal(JSON.stringify(pack).includes('decision'),false);
console.log('Fixed cohort entry: bounded source, legacy hash, complete baseline, no decisions passed');
