// Opt-in real immutable bundle check: browser wind solve versus official Spine Core.
// node tests/check_wind_preview_runtime.mjs bundle-dir official-core-dir output.json
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {performance} from 'node:perf_hooks';
import assert from 'node:assert/strict';
import {validateWindTemplate,jointWindPreview,windOffsets,applyWindOffsets} from '../web/modules/motion-wind-preview.js';

const [folder,coreRoot,output]=process.argv.slice(2);
if(!folder||!coreRoot||!output)throw Error('bundle, official Core and output required');
const hash=raw=>createHash('sha256').update(raw).digest('hex');
const inventory=JSON.parse(await fs.readFile(path.join(folder,'inventory.json')));
const artifact=hash(JSON.stringify(Object.fromEntries(Object.keys(inventory).sort().map(k=>[k,inventory[k]]))));
assert.equal(artifact,path.basename(path.resolve(folder)),'immutable bundle identity');
const read=async name=>{const raw=await fs.readFile(path.join(folder,name));assert.equal(hash(raw),inventory[name],name);return raw;};
const document=JSON.parse(await read('skeleton.json')),report=JSON.parse(await read('joint-animation.json'));
const previewRaw=await read('wind-preview.json');assert.equal(hash(previewRaw),report.secondary.wind_preview.sha256);
const template=validateWindTemplate(JSON.parse(previewRaw),report,document);
const spine=await import(pathToFileURL(path.resolve(coreRoot,'dist/index.js')));
const pkg=JSON.parse(await fs.readFile(path.join(coreRoot,'package.json')));
assert.equal(pkg.name,'@esotericsoftware/spine-core');assert.equal(pkg.version,'4.3.13');
const parser=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(new spine.TextureAtlas((await read('skeleton.atlas')).toString())));
const data=parser.readSkeletonData(document),setup=new Map(document.bones.map(b=>[b.name,b.rotation??0]));
const helperNames=new Set(template.regions.flatMap(r=>r.helpers));
const build=(config,options)=>{const start=performance.now(),value=jointWindPreview(template,report,config,options);return {value,ms:performance.now()-start};};
const baseline=build(report.config),noWind=build(report.config,{noWind:true}),reversedConfig=structuredClone(report.config);
reversedConfig.wind.direction=(reversedConfig.wind.direction+180)%360;
for(const key of reversedConfig.wind.keys)key.direction=(key.direction+180)%360;
const reversed=build(reversedConfig);
let keyError=0;
for(const name of helperNames){const keys=document.animations[report.animation].bones[name].rotate,track=baseline.value.tracks.get(name);
  assert.deepEqual(track.times,keys.map(k=>k.time));
  for(let i=0;i<keys.length;i++)keyError=Math.max(keyError,Math.abs(track.values[i]-keys[i].value));
}
assert.ok(keyError<1e-9,`preview versus baked key error ${keyError}`);
function frame(time,plan){
  const rig=new spine.Skeleton(data),state=new spine.AnimationState(new spine.AnimationStateData(data));
  rig.setupPose();state.setAnimation(0,report.animation,false);state.update(time);state.apply(rig);
  if(plan)applyWindOffsets(rig,windOffsets(plan,time),setup);
  rig.updateWorldTransform(spine.Physics.update);
  const vertices={},locals={};
  for(const bone of rig.bones){const p=bone.appliedPose;locals[bone.data.name]=[p.x,p.y,p.rotation,p.scaleX,p.scaleY,p.shearX,p.shearY];}
  for(const slot of rig.slots){const attachment=slot.appliedPose.attachment;if(!attachment)continue;
    if(attachment instanceof spine.MeshAttachment){const points=new Float32Array(attachment.worldVerticesLength);
      attachment.computeWorldVertices(rig,slot,0,points.length,points,0,2);vertices[slot.data.name]=Array.from(points);
    }else if(attachment instanceof spine.RegionAttachment){const points=new Float32Array(8);
      attachment.computeWorldVertices(slot,attachment.getOffsets(slot.appliedPose),points,0,2);vertices[slot.data.name]=Array.from(points);}
  }
  return {vertices,locals,order:rig.drawOrder.appliedPose.map(s=>s.data.name)};
}
const distance=(a,b)=>Math.max(0,...a.map((v,i)=>Math.abs(v-b[i])));
let poseError=0;const rows=template.regions.map(r=>({slot:r.slot,kind:r.region_kind,no_wind_delta_px:0,reverse_delta_px:0}));
const times=Array.from({length:21},(_,i)=>i*report.duration/20);
for(const time of times){const original=frame(time),same=frame(time,baseline.value),off=frame(time,noWind.value),opposite=frame(time,reversed.value);
  assert.deepEqual(same.order,original.order);
  for(const name of Object.keys(original.vertices))poseError=Math.max(poseError,distance(original.vertices[name],same.vertices[name]));
  for(const name of Object.keys(original.locals))if(!helperNames.has(name)){
    assert.deepEqual(off.locals[name],original.locals[name],`body channel changed: ${name}`);
    assert.deepEqual(opposite.locals[name],original.locals[name],`body channel changed: ${name}`);}
  for(const row of rows){row.no_wind_delta_px=Math.max(row.no_wind_delta_px,distance(original.vertices[row.slot],off.vertices[row.slot]));
    row.reverse_delta_px=Math.max(row.reverse_delta_px,distance(original.vertices[row.slot],opposite.vertices[row.slot]));}
}
assert.ok(poseError<.001,`Runtime preview versus export vertex error ${poseError}`);
for(const row of rows){assert.ok(row.no_wind_delta_px>.001,`${row.slot} no wind did not change response`);
  assert.ok(row.reverse_delta_px>.001,`${row.slot} direction did not change response`);}
const time=report.duration*.63,first=frame(time,reversed.value);frame(report.duration*.17,reversed.value);
assert.deepEqual(frame(time,reversed.value),first,'seeking must not advance solver state');
assert.deepEqual(frame(time),frame(time),'restoring export must be deterministic');
const result={schema:'autospine.wind-preview-runtime-check/v1',artifact_sha256:artifact,core_version:pkg.version,
  duration:report.duration,frames:times.length,helper_bones:helperNames.size,max_key_error_deg:keyError,
  max_baked_pose_vertex_error_px:poseError,seek_error_px:0,body_channels_unchanged:true,
  complete_track_solve_ms:{baseline:baseline.ms,no_wind:noWind.ms,reversed:reversed.ms},regions:rows,
  visual_acceptance:'not_evaluated',passed:true};
await fs.writeFile(output,JSON.stringify(result,null,2));console.log(JSON.stringify(result));
