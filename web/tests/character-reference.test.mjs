import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {readReference} from '../../tools/character-reference.mjs';

test('chunk reader preserves coordinates and rejects changed payload',async()=>{
  const frames=[{time:0,vertices:{leg:[[.123456789012345,3]]}}],bytes=Buffer.from(JSON.stringify(frames));
  const sha=crypto.createHash('sha256').update(bytes).digest('hex');
  const index={schema:'autospine.character-reference-chunks/v1',skeleton_sha256:'a'.repeat(64),
    chunks:[{animation:'walk',part:0,file:`numeric-reference/${sha}.json`,sha256:sha}]};
  const raw=Buffer.from(JSON.stringify(index));
  assert.deepEqual((await readReference(raw,async()=>bytes)).animations.walk,frames);
  await assert.rejects(readReference(raw,async()=>Buffer.from('[]')),/identity/);
  index.chunks[0].file='../outside.json';
  await assert.rejects(readReference(Buffer.from(JSON.stringify(index)),async()=>{throw Error('must not load');}),/identity/);
});

test('legacy references still read unchanged',async()=>{
  const reference={skeleton_sha256:'a'.repeat(64),animations:{idle:[{time:0},{time:1}]}};
  assert.deepEqual(await readReference(Buffer.from(JSON.stringify(reference)),async()=>{throw Error('unexpected');}),reference);
});
