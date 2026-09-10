// Official core numerical verification only. No framebuffer or texture sampling claim.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [folder,coreRoot,reportPath]=process.argv.slice(2);
if(!folder||!coreRoot)throw new Error('usage: folder official-core-package');
const pkg=JSON.parse(await fs.readFile(path.join(coreRoot,'package.json')));
if(pkg.name!=='@esotericsoftware/spine-core'||pkg.version!=='4.3.13')throw new Error('runtime_version_mismatch');
const spine=await import(pathToFileURL(path.resolve(coreRoot,'dist/index.js')));
const digest=b=>crypto.createHash('sha256').update(b).digest('hex');
const raw=await fs.readFile(path.join(folder,'skeleton.json'));
const referenceRaw=await fs.readFile(path.join(folder,'numeric-reference.json'));
const reference=JSON.parse(referenceRaw);
if(reference.skeleton_sha256!==digest(raw))throw new Error('reference_source_mismatch');
const atlasRaw=await fs.readFile(path.join(folder,'skeleton.atlas'));
const atlas=new spine.TextureAtlas(atlasRaw.toString());
const data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(JSON.parse(raw));
if(data.animations.length!==Object.keys(reference.animations).length)throw new Error('animation_inventory_mismatch');
const results=[];
for(const animation of data.animations){
  let maxError=0;
  for(const frame of reference.animations[animation.name]){
    const skeleton=new spine.Skeleton(data),state=new spine.AnimationState(new spine.AnimationStateData(data));
    skeleton.setupPose();state.setAnimation(0,animation.name,false);state.update(frame.time);state.apply(skeleton);
    skeleton.updateWorldTransform(spine.Physics.update);
    if(skeleton.slots.length!==1)throw new Error('region_inventory_mismatch');
    const slot=skeleton.slots[0],attachment=slot.appliedPose.attachment;
    const values=new Float32Array(attachment.worldVerticesLength);
    attachment.computeWorldVertices(skeleton,slot,0,values.length,values,0,2);
    if(values.length!==frame.points.length*2)throw new Error('vertex_inventory_mismatch');
    for(let i=0;i<frame.points.length;i++){
      const error=Math.hypot(values[2*i]-frame.points[i][0],values[2*i+1]-frame.points[i][1]);
      if(!Number.isFinite(error))throw new Error('nonfinite_vertices');maxError=Math.max(maxError,error);
    }
  }
  results.push({animation:animation.name,frames:reference.animations[animation.name].length,max_error_px:maxError,passed:maxError<=.001});
}
const runtimeFiles={};
async function hashTree(dir){for(const entry of (await fs.readdir(dir,{withFileTypes:true})).sort((a,b)=>a.name.localeCompare(b.name))){
 const file=path.join(dir,entry.name);if(entry.isDirectory())await hashTree(file);else if(entry.name.endsWith('.js'))runtimeFiles[path.relative(coreRoot,file).replaceAll('\\','/')]=digest(await fs.readFile(file));
}}
await hashTree(path.join(coreRoot,'dist'));
const report={runtime_package:pkg.name,runtime_version:pkg.version,runtime_files:runtimeFiles,
 skeleton_sha256:digest(raw),atlas_sha256:digest(atlasRaw),reference_sha256:digest(referenceRaw),
 results,passed:results.every(r=>r.passed),scope:'official_core_vertices_only',framebuffer_status:'not_evaluated',
 authority:'none',production_authorized:false};
await fs.writeFile(reportPath||path.join(folder,'official-core-report.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify({passed:report.passed,results}));if(!report.passed)process.exitCode=1;
