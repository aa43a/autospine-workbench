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

test('clipped source seeks in candidate time and restores controls after failure',()=>{
  const seen=[],status={},inputs={play:{disabled:false},motion:{disabled:true},time:{disabled:false}};
  const sync=createCohortSync(status),win={characterPlayerState:{duration:1},
    characterPlayerControl:{artifact:'a',seek:t=>{seen.push(t);return true;}},
    document:{getElementById:id=>inputs[id]}};
  sync.seek(1.75,2);sync.attach({contentWindow:win},'a',{start:1,end:2});
  sync.seek(1.25,2);assert.deepEqual(seen,[.75,.25]);assert.equal(inputs.play.disabled,true);
  assert.match(status.textContent,/源 1.000–2.000 秒 ↔ 角色 0–1.000 秒/);
  win.characterPlayerControl.artifact='changed';sync.seek(1.5,2);
  assert.equal(inputs.play.disabled,false);assert.equal(inputs.motion.disabled,true);
  assert.equal(inputs.time.disabled,false);assert.equal(seen.length,2);sync.clear();
});

test('range mismatch is refused and reattachment stops the old target',()=>{
  const seen=[],status={},sync=createCohortSync(status);
  const frame=artifact=>({contentWindow:{characterPlayerControl:{artifact,seek:t=>{seen.push([artifact,t]);return true;}},characterPlayerState:{duration:1}}});
  sync.seek(1.5,2);sync.attach(frame('a'),'a',{start:1,end:2});
  sync.attach(frame('b'),'b',{start:1,end:2});sync.seek(1.1,2);
  assert.deepEqual(seen.map(r=>r[0]),['a','b','b']);
  sync.seek(.5,2);assert.match(status.textContent,/源片段时间不匹配/);
  assert.equal(seen.length,3);sync.clear();
});

test('depth isolation and restore preserve time and reject stale identity',()=>{
 const calls=[],status={},sync=createCohortSync(status);
 const control={artifact:'a',seek:()=>assert.fail('isolation must not seek'),inspectRegions:(...args)=>{calls.push(args);return true;}};
 sync.attach({contentWindow:{characterPlayerControl:control}},'a');
 assert.equal(sync.regions(['arm','torso']),true);
 assert.equal(sync.regions([],'full'),true);
 assert.deepEqual(calls,[[['arm','torso'],'isolate'],[[],'full']]);
 control.artifact='old';assert.equal(sync.regions(['arm','torso']),false);
 assert.equal(calls.length,2);sync.clear();assert.equal(sync.regions([],'full'),false);
});
