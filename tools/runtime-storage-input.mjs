// Bounded, lossless transport for large sampled storage references.
import {gunzipSync} from 'node:zlib';

export function decodeStorageReference(raw, {inputLimit=64*1024*1024, outputLimit=256*1024*1024}={}) {
  if(raw.length>inputLimit)throw Error('runtime_storage_reference_limit');
  if(raw[0]===0x1f&&raw[1]===0x8b)return gunzipSync(raw,{maxOutputLength:outputLimit});
  return raw;
}
