// Official Runtime CPU vertices for explicitly sampled corrective poses; no browser/GPU.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import vm from 'node:vm';
import {dirname,join} from 'node:path';
import {readReference} from './character-reference.mjs';

const [fixturePath,runtimePath]=process.argv.slice(2);
const input=JSON.parse(readFileSync(fixturePath,'utf8')),runtime=readFileSync(runtimePath);
assert.equal(createHash('sha256').update(runtime).digest('hex'),input.runtime_sha256);
const skeletonBytes=readFileSync(join(dirname(fixturePath),'skeleton.json'));
assert.equal(createHash('sha256').update(skeletonBytes).digest('hex'),input.skeleton_sha256);
assert.deepEqual(JSON.parse(skeletonBytes),input.skeleton);
let referenceFrames=null;
if(input.reference_bundle){
 const root=input.reference_bundle,inventory=JSON.parse(readFileSync(join(root,'inventory.json')));
 const load=async name=>{const raw=readFileSync(join(root,name));assert.equal(createHash('sha256').update(raw).digest('hex'),inventory[name]);return raw;};
 const reference=await readReference(await load('numeric-reference.json'),load);
 assert.equal(reference.skeleton_sha256,input.skeleton_sha256);
 referenceFrames=reference.animations[input.animation].length;assert.equal(referenceFrames,input.reference_frames);
}
const sandbox={console};vm.createContext(sandbox);vm.runInContext(runtime.toString(),sandbox);
const {spine}=sandbox,atlas=new spine.TextureAtlas(input.atlas);
const data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(input.skeleton);
let maximum=0,vertices=0;
for(const frame of input.samples){
 const skeleton=new spine.Skeleton(data),state=new spine.AnimationState(new spine.AnimationStateData(data));
 skeleton.setupPose();state.setAnimation(0,input.animation,false);state.update(frame.time);state.apply(skeleton);
 skeleton.updateWorldTransform(spine.Physics.update);
 for(const [slotName,expected] of Object.entries(frame.vertices)){
  const slot=skeleton.findSlot(slotName),attachment=slot.appliedPose.attachment;
  assert.ok(attachment instanceof spine.MeshAttachment);assert.equal(attachment.worldVerticesLength,expected.length*2);
  const actual=new Float32Array(attachment.worldVerticesLength);
  attachment.computeWorldVertices(skeleton,slot,0,actual.length,actual,0,2);
  for(let i=0;i<expected.length;i++){
   const error=Math.hypot(actual[i*2]-expected[i][0],actual[i*2+1]-expected[i][1]);
   assert.ok(Number.isFinite(error));maximum=Math.max(maximum,error);vertices++;
  }
 }
}
assert.ok(maximum<=.01,`Runtime vertex error ${maximum}`);
console.log(JSON.stringify({source_candidate:input.source_candidate,skeleton_sha256:input.skeleton_sha256,
 runtime_sha256:input.runtime_sha256,frames:input.samples.length,reference_frames:referenceFrames,vertices,maximum_error_px:maximum,
 limit_px:.01,passed:true,scope:'sampled_official_runtime_cpu_vertices_no_gpu_capture_or_visual_acceptance',
 authority:'none',selected:false}));
