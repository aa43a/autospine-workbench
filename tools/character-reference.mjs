import crypto from 'node:crypto';
export async function readReference(raw, load) {
  const value=JSON.parse(raw);
  if(value.schema===undefined)return value;
  if(value.schema!=='autospine.character-reference-chunks/v1'||!Array.isArray(value.chunks)||!value.chunks.length||value.chunks.length>1024)
    throw Error('character_reference_chunks_invalid');
  const animations=Object.create(null),counts=new Map();let total=0;
  for(const row of value.chunks){
    if(!/^[a-f0-9]{64}$/.test(row.sha256)||row.file!==`numeric-reference/${row.sha256}.json`||row.part!==(counts.get(row.animation)||0))
      throw Error('character_reference_chunk_identity');
    const bytes=await load(row.file);total+=bytes.length;
    if(bytes.length>64*1024*1024||total>256*1024*1024||crypto.createHash('sha256').update(bytes).digest('hex')!==row.sha256)
      throw Error('character_reference_chunk_identity');
    const frames=JSON.parse(bytes);
    if(!Array.isArray(frames)||!frames.length||frames.length>128)throw Error('character_reference_chunk_frames');
    (animations[row.animation]??=[]).push(...frames);counts.set(row.animation,row.part+1);
  }
  return {skeleton_sha256:value.skeleton_sha256,animations};
}
