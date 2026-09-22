import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';
const code = await readFile(new URL('../modules/motion-cohort-sync.js', import.meta.url), 'utf8');
const {createCohortSync} = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));

test('exact candidate seeks forward/backward and clears previous target', () => {
  const seen=[], status={};
  const sync=createCohortSync(status);
  sync.seek(2,4);
  sync.attach({contentWindow:{characterPlayerControl:{artifact:'a',seek:t=>{seen.push(t);return true;}},characterPlayerState:{duration:4}}},'a');
  sync.seek(.5,4); sync.clear(); sync.seek(3,4);
  assert.deepEqual(seen,[2,.5]);
});

test('region inspection refuses mismatched candidates and forwards exact triangle',()=>{
 const calls=[],status={},sync=createCohortSync(status);
 const control={artifact:'a',inspectTriangle:(...args)=>{calls.push(args);return true;}};
 sync.attach({contentWindow:{characterPlayerControl:control}},'a');
 assert.equal(sync.inspect('leg',73,'motion'),true);
 assert.deepEqual(calls,[['leg',73,'motion']]);
 control.artifact='old';assert.equal(sync.inspect('leg',74,'motion'),false);
 assert.equal(calls.length,1);sync.clear();
});
test('candidate identity or duration mismatch never drives target', () => {
  for(const [identity,duration] of [['wrong',4],['a',2]]) {
    const status={},sync=createCohortSync(status);
    sync.seek(1,4);
    sync.attach({contentWindow:{characterPlayerControl:{artifact:identity,seek:()=>assert.fail('invalid seek')},characterPlayerState:{duration}}},'a');
    assert.match(status.textContent,/同步未启用/); sync.clear();
  }
});
