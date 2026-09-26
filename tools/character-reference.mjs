import crypto from 'node:crypto';
import {gunzipSync} from 'node:zlib';
function decompress(raw) {
  try {
    const value=JSON.parse(raw),limit=64*1024*1024;
    if(Object.keys(value).sort().join(',')!=='bytes,codec,data,sha256'||value.codec!=='gzip-base64-json-v1'||
      !Number.isSafeInteger(value.bytes)||value.bytes<1||value.bytes>limit||typeof value.data!=='string')throw Error();
    const compressed=Buffer.from(value.data,'base64');
    if(compressed.length>limit||compressed.toString('base64')!==value.data)throw Error();
    const bytes=gunzipSync(compressed,{maxOutputLength:value.bytes});
    if(bytes.length!==value.bytes||crypto.createHash('sha256').update(bytes).digest('hex')!==value.sha256)throw Error();
    return bytes;
  }catch{throw Error('character_reference_compressed_chunk_invalid');}
}
export async function readReference(raw, load) {
  const value=JSON.parse(raw);
  if(value.schema===undefined)return value;
  if(!['autospine.character-reference-chunks/v1','autospine.character-reference-chunks/v2'].includes(value.schema)||!Array.isArray(value.chunks)||!value.chunks.length||value.chunks.length>1024)
    throw Error('character_reference_chunks_invalid');
  const animations=Object.create(null),counts=new Map();let total=0,decodedTotal=0;
  for(const row of value.chunks){
    if(!/^[a-f0-9]{64}$/.test(row.sha256)||row.file!==`numeric-reference/${row.sha256}.json`||row.part!==(counts.get(row.animation)||0))
      throw Error('character_reference_chunk_identity');
    const bytes=await load(row.file);total+=bytes.length;
    if(bytes.length>64*1024*1024||total>256*1024*1024||crypto.createHash('sha256').update(bytes).digest('hex')!==row.sha256)
      throw Error('character_reference_chunk_identity');
    const decoded=value.schema==='autospine.character-reference-chunks/v2'?decompress(bytes):bytes;
    decodedTotal+=decoded.length;if(decodedTotal>256*1024*1024)throw Error('character_reference_decoded_limit');
    const frames=JSON.parse(decoded);
    if(!Array.isArray(frames)||!frames.length||frames.length>128)throw Error('character_reference_chunk_frames');
    (animations[row.animation]??=[]).push(...frames);counts.set(row.animation,row.part+1);
  }
  return {skeleton_sha256:value.skeleton_sha256,animations};
}
