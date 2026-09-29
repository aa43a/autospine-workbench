// Opt-in numerical check of the browser amplitude preview against official Core.
// Usage: node tests/check_joint_preview_runtime.mjs fixture.json joint-animation.json core-root report.json [exact-skeleton.json]
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {performance} from 'node:perf_hooks';
import {jointAmplitudePreview,applyJointAmplitude} from '../web/modules/motion-joint-preview.js';

const [fixturePath,jointPath,coreRoot,outputPath,exactSkeletonPath]=process.argv.slice(2);
if(!fixturePath||!jointPath||!coreRoot||!outputPath)throw Error('fixture, joint report, official core and output required');
const spine=await import(pathToFileURL(path.resolve(coreRoot,'dist/index.js')));
const pkg=JSON.parse(await fs.readFile(path.join(coreRoot,'package.json')));
assert.equal(pkg.name,'@esotericsoftware/spine-core');assert.equal(pkg.version,'4.3.13');
const hash=value=>crypto.createHash('sha256').update(value).digest('hex');
const fixtureBytes=await fs.readFile(fixturePath),jointBytes=await fs.readFile(jointPath);
const fixture=JSON.parse(fixtureBytes),joint=JSON.parse(jointBytes),document=fixture.skeleton;
if(exactSkeletonPath){const exact=await fs.readFile(exactSkeletonPath);assert.equal(hash(exact),joint.skeleton_sha256);
  assert.deepEqual(document,JSON.parse(exact),'fixture must use the exact candidate skeleton');}
assert.deepEqual(joint.secondary.regions,fixture.secondary.regions,'fixture and current candidate region identities');
assert.equal(joint.animation,fixture.animation);
const hashes={skeleton:hash(JSON.stringify(document)),config:hash(JSON.stringify(joint.config)),report:hash(JSON.stringify(joint))};
const parser=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(new spine.TextureAtlas(fixture.atlas)));
const data=parser.readSkeletonData(document),setup=new Map(document.bones.map(b=>[b.name,b.rotation??0]));
const helperNames=new Set(joint.secondary.regions.flatMap(row=>row.helpers)),localFields=['x','y','rotation','scaleX','scaleY','shearX','shearY'];
function sample(time,gains){
  // Match editor draw: fresh Skeleton/AnimationState, deterministic same-time seek.
  const rig=new spine.Skeleton(data),state=new spine.AnimationState(new spine.AnimationStateData(data));
  rig.setupPose();state.setAnimation(0,fixture.animation,false);state.update(time);state.apply(rig);
  applyJointAmplitude(rig,gains,setup);rig.updateWorldTransform(spine.Physics.update);
  const vertices={},locals={},matrices={};
  for(const bone of rig.bones){const p=bone.appliedPose;
    locals[bone.data.name]=Object.fromEntries(localFields.map(k=>[k,p[k]]));
    matrices[bone.data.name]=[p.a,p.b,p.c,p.d,p.worldX,p.worldY];
  }
  for(const slot of rig.slots){const attachment=slot.appliedPose.attachment;if(!attachment)continue;
    const points=new Float32Array(attachment.worldVerticesLength);
    attachment.computeWorldVertices(rig,slot,0,points.length,points,0,2);vertices[slot.data.name]=Array.from(points);
  }
  return {vertices,locals,matrices,order:rig.drawOrder.appliedPose.map(s=>s.data.name)};
}
function maxDifference(a,b){
  let result=0;
  for(const key of Object.keys(a)){assert.ok(Object.hasOwn(b,key));assert.equal(a[key].length,b[key].length);
    for(let i=0;i<a[key].length;i++)result=Math.max(result,Math.abs(a[key][i]-b[key][i]));}
  return result;
}
function maxVertexDistance(a,b){
  let result=0;for(const key of Object.keys(a)){assert.equal(a[key].length,b[key].length);
    for(let i=0;i<a[key].length;i+=2)result=Math.max(result,Math.hypot(a[key][i]-b[key][i],a[key][i+1]-b[key][i+1]));}
  return result;
}
const frames=[],time=6,original=sample(time,null),plans=new Map();
for(const strength of [1,.5,0]){
  const config=structuredClone(joint.config);
  for(const group of ['hair','cloth','objects']){
    config[group].strength=strength;
    for(const values of Object.values(config[group].overrides??{}))if(Object.hasOwn(values,'strength'))values.strength=strength;
  }
  const preview=jointAmplitudePreview(document,joint,config);assert.equal(preview.available,true);assert.deepEqual(preview.pending,[]);
  const frame=sample(time,preview.gains);plans.set(strength,preview);
  for(const [name,local]of Object.entries(frame.locals))if(!helperNames.has(name))
    assert.deepEqual(local,original.locals[name],`non-response bone ${name} changed at strength ${strength}`);
  assert.deepEqual(frame.order,original.order);
  frames.push({strength,frame,vertex_delta_px:maxVertexDistance(frame.vertices,original.vertices),matrix_delta:maxDifference(frame.matrices,original.matrices)});
}
assert.equal(frames[0].vertex_delta_px,0,'identity strength must match baked output exactly');
assert.ok(frames[1].vertex_delta_px>1e-5);assert.ok(frames[2].vertex_delta_px>frames[1].vertex_delta_px);
for(const row of joint.secondary.regions){
  assert.ok(maxDifference({[row.slot]:frames[1].frame.vertices[row.slot]},{[row.slot]:original.vertices[row.slot]})>1e-6,`${row.region_kind}/${row.slot} preview did not move`);
}
const first=sample(6,plans.get(.5).gains);sample(2,plans.get(.5).gains);const repeated=sample(6,plans.get(.5).gains);
const seekError=maxDifference(first.matrices,repeated.matrices),seekVertexError=maxDifference(first.vertices,repeated.vertices);
assert.equal(seekError,0);assert.equal(seekVertexError,0);
const restored=sample(6,null),restoreError=maxDifference(original.vertices,restored.vertices);assert.equal(restoreError,0);
assert.equal(hash(JSON.stringify(document)),hashes.skeleton);assert.equal(hash(JSON.stringify(joint.config)),hashes.config);assert.equal(hash(JSON.stringify(joint)),hashes.report);
assert.equal(hash(await fs.readFile(fixturePath)),hash(fixtureBytes));assert.equal(hash(await fs.readFile(jointPath)),hash(jointBytes));

// Short isolated microbenchmark: no I/O, WebGL, geometry QA or full spring solve.
const draft=structuredClone(joint.config);for(const group of ['hair','cloth','objects'])draft[group].strength=.5;
const rig=new spine.Skeleton(data);rig.setupPose();const baseline=rig.bones.map(b=>b.pose.rotation);
function stats(values){const sorted=values.toSorted((a,b)=>a-b);return {median_ms:sorted[Math.floor(sorted.length*.5)],p95_ms:sorted[Math.floor(sorted.length*.95)],max_ms:sorted.at(-1)};}
for(let i=0;i<30;i++){jointAmplitudePreview(document,joint,draft);applyJointAmplitude(rig,plans.get(.5).gains,setup);rig.bones.forEach((b,j)=>{b.pose.rotation=baseline[j];});}
const planning=[],applying=[];
for(let i=0;i<500;i++){
  let start=performance.now();jointAmplitudePreview(document,joint,draft);planning.push(performance.now()-start);
  start=performance.now();applyJointAmplitude(rig,plans.get(.5).gains,setup);applying.push(performance.now()-start);
  rig.bones.forEach((b,j)=>{b.pose.rotation=baseline[j];});
}
const report={profile:'joint-amplitude-preview-official-core-v1',passed:true,runtime_package:pkg.name,runtime_version:pkg.version,
  fixture_sha256:hash(fixtureBytes),joint_report_sha256:hash(jointBytes),skeleton_sha256:joint.skeleton_sha256,
  character:'alice',time_seconds:time,helper_count:helperNames.size,bone_count:data.bones.length,
  strengths:frames.map(({frame,...row})=>row),non_helper_local_tracks_unchanged:true,draw_order_unchanged:true,
  reverse_seek_matrix_error:seekError,reverse_seek_vertex_error_px:seekVertexError,preview_disabled_vertex_error_px:restoreError,
  input_document_and_config_unchanged:true,exact_candidate_skeleton_verified:Boolean(exactSkeletonPath),
  microbenchmark:{iterations:500,planning:stats(planning),apply:stats(applying),scope:'pure amplitude planning and local helper application only; excludes rendering, DOM, loading and full physics'},
  limitations:['amplitude comparison of baked helper trajectories, not a new spring solve','new geometry and collision QA not evaluated','framebuffer not captured by this Core check'],
  visual_acceptance:'not_evaluated'};
await fs.mkdir(path.dirname(outputPath),{recursive:true});await fs.writeFile(outputPath,JSON.stringify(report,null,2));
console.log(JSON.stringify(report));
