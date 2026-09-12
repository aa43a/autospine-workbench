// Opt-in official core verification of all attachments in the composed character.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';
import {readReference} from './character-reference.mjs';
const [folder, coreRoot, output] = process.argv.slice(2);
if (!folder || !coreRoot || !output) throw new Error('usage: bundle official-core output');
const pkg = JSON.parse(await fs.readFile(path.join(coreRoot,'package.json')));
if(pkg.name !== '@esotericsoftware/spine-core' || pkg.version !== '4.3.13') throw new Error('runtime_version_mismatch');
const spine = await import(pathToFileURL(path.resolve(coreRoot,'dist/index.js')));
const hash = raw => crypto.createHash('sha256').update(raw).digest('hex');
const raw = await fs.readFile(path.join(folder,'skeleton.json'));
const atlasRaw = await fs.readFile(path.join(folder,'skeleton.atlas'));
const referenceRaw = await fs.readFile(path.join(folder,'numeric-reference.json'));
const reference = await readReference(referenceRaw,name=>fs.readFile(path.join(folder,name)));
if(reference.skeleton_sha256 !== hash(raw)) throw new Error('reference_source_mismatch');
const atlas = new spine.TextureAtlas(atlasRaw.toString());
const data = new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(JSON.parse(raw));
if(JSON.stringify(data.animations.map(a=>a.name).sort()) !== JSON.stringify(Object.keys(reference.animations).sort())) throw new Error('animation_inventory_mismatch');
const results = [];
for(const animation of data.animations){
  let error = 0, probes = 0;
  for(const frame of reference.animations[animation.name]){
    const skeleton = new spine.Skeleton(data), state = new spine.AnimationState(new spine.AnimationStateData(data));
    skeleton.setupPose(); state.setAnimation(0,animation.name,false); state.update(frame.time); state.apply(skeleton);
    skeleton.updateWorldTransform(spine.Physics.update);
    if(JSON.stringify(skeleton.slots.map(s=>s.data.name).sort()) !== JSON.stringify(Object.keys(frame.vertices).sort())) throw new Error('slot_inventory_mismatch');
    for(const slot of skeleton.slots){
      const attachment = slot.appliedPose.attachment, points = frame.vertices[slot.data.name];
      const vertices = new Float32Array(attachment.worldVerticesLength);
      attachment.computeWorldVertices(skeleton,slot,0,vertices.length,vertices,0,2);
      if(vertices.length !== points.length*2) throw new Error('vertex_inventory_mismatch');
      for(let i=0;i<points.length;i++){
        const delta = Math.hypot(vertices[i*2]-points[i][0],vertices[i*2+1]-points[i][1]);
        if(!Number.isFinite(delta)) throw new Error('nonfinite_vertices');
        error = Math.max(error,delta); probes++;
      }
    }
  }
  results.push({animation:animation.name,frames:reference.animations[animation.name].length,probes,max_error_px:error,passed:error<=.001});
}
const runtimeFiles = {};
async function inventory(dir){for(const e of await fs.readdir(dir,{withFileTypes:true})){
  const file=path.join(dir,e.name);if(e.isDirectory()) await inventory(file);
  else if(e.name.endsWith('.js')) runtimeFiles[path.relative(coreRoot,file).replaceAll('\\','/')]=hash(await fs.readFile(file));
}}
await inventory(path.join(coreRoot,'dist'));
const report = {runtime_package:pkg.name,runtime_version:pkg.version,runtime_files:runtimeFiles,
  skeleton_sha256:hash(raw),atlas_sha256:hash(atlasRaw),reference_sha256:hash(referenceRaw),results,
  reference_reader_sha256:hash(await fs.readFile(new URL('./character-reference.mjs',import.meta.url))),
  passed:results.every(r=>r.passed),scope:'official_core_all_attachment_vertices',framebuffer_status:'not_evaluated',authority:'none',production_authorized:false};
await fs.writeFile(output,JSON.stringify(report,null,2));
console.log(JSON.stringify({passed:report.passed,results}));if(!report.passed)process.exitCode=1;
