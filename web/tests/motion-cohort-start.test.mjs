import assert from 'node:assert/strict';
import {test} from 'node:test';
import {startCohort} from '../modules/motion-cohort-start.js';
test('module failure replaces indefinite loading; success preserves application state',async()=>{
  const status={textContent:'loading'};
  assert.equal(await startCohort(async()=>{throw Error('missing export');},status),false);
  assert.match(status.textContent,/missing export/);
  assert.equal(await startCohort(async()=>{status.textContent='ready';},status),true);
  assert.equal(status.textContent,'ready');
});
