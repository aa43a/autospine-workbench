import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {gzipSync} from 'node:zlib';
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

test('compressed chunks reconstruct exact numbers and reject decompression size lies',async()=>{
  const original=Buffer.from('[{"time":0.00000001,"vertices":{"leg":[[-0.0,0.123456789012345]]}}]');
  const envelope={codec:'gzip-base64-json-v1',bytes:original.length,
    sha256:crypto.createHash('sha256').update(original).digest('hex'),data:gzipSync(original).toString('base64')};
  const read=async value=>{
    const bytes=Buffer.from(JSON.stringify(value)),sha=crypto.createHash('sha256').update(bytes).digest('hex');
    const index={schema:'autospine.character-reference-chunks/v2',skeleton_sha256:'a'.repeat(64),
      chunks:[{animation:'walk',part:0,file:`numeric-reference/${sha}.json`,sha256:sha}]};
    return readReference(Buffer.from(JSON.stringify(index)),async()=>bytes);
  };
  const decoded=await read(envelope);
  assert.deepEqual(decoded.animations.walk,JSON.parse(original));
  assert.ok(Object.is(decoded.animations.walk[0].vertices.leg[0][0],-0));
  for(const changed of [{bytes:1},{bytes:64*1024*1024+1},{codec:'unsupported'},{data:'%%%'},{sha256:'0'.repeat(64)}])
    await assert.rejects(read({...envelope,...changed}),/compressed_chunk_invalid/);
});
