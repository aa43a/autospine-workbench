import assert from 'node:assert/strict';
import {gzipSync} from 'node:zlib';
import {decodeStorageReference} from '../tools/runtime-storage-input.mjs';

const raw=Buffer.from('{"value":"'+ 'x'.repeat(1000)+'"}');
assert.deepEqual(decodeStorageReference(raw),raw);
assert.deepEqual(decodeStorageReference(gzipSync(raw)),raw);
assert.throws(()=>decodeStorageReference(raw,{inputLimit:100}),/reference_limit/);
assert.throws(()=>decodeStorageReference(gzipSync(raw),{outputLimit:100}));
assert.throws(()=>decodeStorageReference(Buffer.from([0x1f,0x8b,0x00])));
console.log('storage transport: lossless plain/gzip and size/corruption boundaries passed');
