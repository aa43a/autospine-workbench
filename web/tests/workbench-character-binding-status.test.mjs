import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {needsBindingReview} from '../modules/workbench-character-ledger.js';

test('completion follows actions using the shared backend matrix',async()=>{
 const cases=JSON.parse(await readFile(new URL('../../tests/fixtures/character-binding-status.json',import.meta.url),'utf8'));
 for(const c of cases)assert.equal(needsBindingReview(c.layer,c.confirmed),c.expected,c.name);
});
