// Prove typed-array deform identity with the actual official parser.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [beforeFolder,afterFolder,coreRoot]=process.argv.slice(2);
const hash=b=>createHash('sha256').update(b).digest('hex');
const pkg=JSON.parse(await fs.readFile(path.join(coreRoot,'package.json')));
assert.equal(pkg.name,'@esotericsoftware/spine-core');assert.equal(pkg.version,'4.3.13');
const spine=await import(pathToFileURL(path.resolve(coreRoot,'dist/index.js')));
const raws=await Promise.all([beforeFolder,afterFolder].map(p=>fs.readFile(path.join(p,'after/runtime/player-assets/scene.json'))));
const receipts=await Promise.all([beforeFolder,afterFolder].map(async p=>JSON.parse(await fs.readFile(path.join(p,'report.json')))));
const scenes=raws.map(r=>JSON.parse(r));
for(let i=0;i<2;i++)assert.equal(scenes[i].artifact_sha256,receipts[i].candidate);
assert.equal(receipts[0].parent,receipts[1].parent);assert.equal(scenes[0].atlas,scenes[1].atlas);assert.deepEqual(scenes[0].textures,scenes[1].textures);
const parsed=scenes.map(scene=>new spine.SkeletonJson(new spine.AtlasAttachmentLoader(new spine.TextureAtlas(scene.atlas))).readSkeletonData(scene.skeleton));
let frames=0,values=0;
assert.equal(parsed[0].animations.length,parsed[1].animations.length);
for(let a=0;a<parsed[0].animations.length;a++){
 const [before,after]=parsed.map(d=>d.animations[a]);assert.equal(before.name,after.name);assert.equal(before.duration,after.duration);assert.equal(before.timelines.length,after.timelines.length);
 for(let i=0;i<before.timelines.length;i++){
  const first=before.timelines[i],second=after.timelines[i];assert.equal(first.constructor.name,second.constructor.name);
  if(!(first instanceof spine.DeformTimeline))continue;
  assert.deepEqual(first.frames,second.frames);assert.deepEqual(first.curves,second.curves);assert.equal(first.vertices.length,second.vertices.length);
  for(let j=0;j<first.vertices.length;j++){
   assert.ok(first.vertices[j] instanceof Float32Array);assert.ok(second.vertices[j] instanceof Float32Array);
   const bytes=v=>Buffer.from(v.buffer,v.byteOffset,v.byteLength);
   assert.ok(bytes(first.vertices[j]).equals(bytes(second.vertices[j])),'deform import changed');frames++;values+=first.vertices[j].length;
  }
 }
}
// Verify everything outside deform values is untouched as well.
for(const scene of scenes)for(const animation of Object.values(scene.skeleton.animations))
 for(const skin of Object.values(animation.attachments??{}))for(const slot of Object.values(skin))for(const att of Object.values(slot))
  for(const frame of att.deform??[])if('vertices' in frame)frame.vertices=frame.vertices.map(()=>0);
assert.deepEqual(scenes[0].skeleton,scenes[1].skeleton);
const report={passed:true,authority:'none',selected:false,runtime_version:pkg.version,source_candidate:receipts[0].candidate,candidate:receipts[1].candidate,
 scene_sha256:raws.map(hash),parser_sha256:hash(await fs.readFile(path.join(coreRoot,'dist/SkeletonJson.js'))),frames,values,
 scope:'official_parser_deform_float32_bit_identity_and_other_json_fields_unchanged',framebuffer_status:'not_evaluated'};
await fs.writeFile(path.join(afterFolder,'storage-check.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
