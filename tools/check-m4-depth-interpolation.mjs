// Compare actual official clip vertices with independently replayed source-depth fields.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [folder,fieldPath,coreRoot,output]=process.argv.slice(2);
const hash=b=>createHash('sha256').update(b).digest('hex');
const pkg=JSON.parse(await fs.readFile(path.join(coreRoot,'package.json')));
assert.equal(pkg.name,'@esotericsoftware/spine-core');assert.equal(pkg.version,'4.3.13');
const spine=await import(pathToFileURL(path.resolve(coreRoot,'dist/index.js')));
const raw=await fs.readFile(fieldPath),field=JSON.parse(raw);
const receipt=JSON.parse(await fs.readFile(path.join(folder,'report.json')));
assert.equal(field.candidate,receipt.parent);
assert.ok(receipt.experiment?.sampled_boundary_error_pixels==null,'grouped clips need a different reader');
const sceneRaws=await Promise.all(['before','after'].map(n=>fs.readFile(path.join(folder,n,'runtime/player-assets/scene.json'))));
const [before,after]=sceneRaws.map(r=>JSON.parse(r));
assert.equal(before.artifact_sha256,receipt.parent);assert.equal(after.artifact_sha256,receipt.candidate);
function rig(scene){const atlas=new spine.TextureAtlas(scene.atlas),data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(scene.skeleton);
 return {skeleton:new spine.Skeleton(data),state:new spine.AnimationState(new spine.AnimationStateData(data))};}
const source=rig(before),candidate=rig(after);
const mesh=before.skeleton.skins[0].attachments[field.arm][field.arm],triangles=mesh.triangles;
const names=after.skeleton.slots.filter(s=>/^m4-tri-front-\d+-clip$/.test(s.name)).map(s=>s.name);
assert.ok(names.length>0);
const uvIndex=new Map();for(let i=0;i<mesh.uvs.length;i+=2){const key=JSON.stringify(mesh.uvs.slice(i,i+2));assert.ok(!uvIndex.has(key),'ambiguous source UV identity');uvIndex.set(key,i/2);}
const staticParts=[];
for(const side of ['front','back']){
 const name=`m4-tri-${side}-static`,part=after.skeleton.skins[0].attachments[name]?.[name];if(!part)continue;
 const indices=[];for(let i=0;i<part.uvs.length;i+=2){const index=uvIndex.get(JSON.stringify(part.uvs.slice(i,i+2)));assert.notEqual(index,undefined);indices.push(index);}
 staticParts.push({side,name,indices,triangles:part.triangles});
}
function pose(r,time){r.skeleton.setupPose();r.state.setAnimation(0,'external-motion',false);r.state.update(time);r.state.apply(r.skeleton);r.skeleton.updateWorldTransform(spine.Physics.update);}
function points(r,name){const slot=r.skeleton.findSlot(name);assert.ok(slot);const att=slot.appliedPose.attachment;
 const values=new Float32Array(att.worldVerticesLength);att.computeWorldVertices(r.skeleton,slot,0,values.length,values,0,2);
 return Array.from({length:values.length/2},(_,i)=>[values[i*2],values[i*2+1]]);}
const cross=(a,b)=>a[0]*b[1]-a[1]*b[0],sub=(a,b)=>[a[0]-b[0],a[1]-b[1]];
function inside(poly,p){const signs=poly.map((a,i)=>cross(sub(poly[(i+1)%poly.length],a),sub(p,a)));
 return signs.every(x=>x>=-1e-6)||signs.every(x=>x<=1e-6);}
function gradient(p,v){const a=sub(p[1],p[0]),b=sub(p[2],p[0]),det=cross(a,b);assert.ok(Math.abs(det)>1e-8);
 return [(v[1]-v[0])*b[1]/det-(v[2]-v[0])*a[1]/det,(v[2]-v[0])*a[0]/det-(v[1]-v[0])*b[0]/det];}
const rows=[];let totalProbes=0,negativeControl=0;
for(const frame of field.rows){
 pose(source,frame.time);pose(candidate,frame.time);const world=points(source,field.arm);
 let unknown=0,mismatch=0,maxMismatchDistance=0,maxBoundaryError=0,worstTriangle=null,staticMismatches=0,staticWorldError=0;
 for(const part of staticParts){const actual=points(candidate,part.name);
  for(let i=0;i<part.indices.length;i++)staticWorldError=Math.max(staticWorldError,Math.hypot(...sub(actual[i],world[part.indices[i]])));
  for(const index of new Set(part.triangles.map(i=>part.indices[i]))){const value=frame.depth_values[index];
   if(value===null){unknown++;continue;}if(Math.abs(value)>1e-10&&(value>0)!==(part.side==='front'))staticMismatches++;
  }
 }
 for(const name of names){
  const index=Number(name.match(/-(\d+)-clip$/)[1]),ids=triangles.slice(index*3,index*3+3);
  assert.equal(ids.length,3);const p=ids.map(i=>world[i]),v=ids.map(i=>frame.depth_values[i]);
  if(v.some(x=>x===null)){unknown++;continue;}assert.ok(v.every(Number.isFinite));
  const quad=points(candidate,name);assert.equal(quad.length,4);
  const g=gradient(p,v),length=Math.hypot(...g),edge=sub(quad[3],quad[0]),edgeLength=Math.hypot(...edge);
  assert.ok(edgeLength>1e-8);
  for(let a=0;a<3;a++){const b=(a+1)%3;
   if(v[a]*v[b]<0){const t=v[a]/(v[a]-v[b]),q=[p[a][0]+t*(p[b][0]-p[a][0]),p[a][1]+t*(p[b][1]-p[a][1])];
    const error=Math.abs(cross(edge,sub(q,quad[0])))/edgeLength;
    if(error>maxBoundaryError){maxBoundaryError=error;worstTriangle=index;}
   }
  }
  for(let a=0;a<=8;a++)for(let b=0;b<=8-a;b++){
   const weights=[a/8,b/8,1-(a+b)/8],value=weights.reduce((s,w,i)=>s+w*v[i],0);
   if(Math.abs(value)<1e-10)continue;const q=[0,1].map(k=>weights.reduce((s,w,i)=>s+w*p[i][k],0));totalProbes++;
   const actual=inside(quad,q);if(!actual!==(value>0))negativeControl++;
   if(actual!==(value>0)){mismatch++;maxMismatchDistance=Math.max(maxMismatchDistance,length>1e-12?Math.abs(value)/length:Infinity);}
  }
 }
 rows.push({time:frame.time,unknown_samples:unknown,mismatched_probes:mismatch,static_vertex_mismatches:staticMismatches,static_world_error_px:staticWorldError,max_mismatch_distance_px:maxMismatchDistance,max_boundary_error_px:maxBoundaryError,worst_triangle:worstTriangle});
}
assert.ok(negativeControl>0,'reversed-side control must disagree');
const report={authority:'none',selected:false,candidate:receipt.candidate,parent:receipt.parent,runtime_version:pkg.version,
 field_sha256:hash(raw),scene_sha256:sceneRaws.map(hash),parser_sha256:hash(await fs.readFile(path.join(coreRoot,'dist/SkeletonJson.js'))),
 profile:'official-clip-vs-replayed-source-field-v1',scope:'front_clip_geometry_and_static_signs_against_proxy_not_visible_pixels_or_true_surface',
 limitations:['proximal_material_override_not_evaluated','sampled_times_not_continuous_proof'],negative_control_reversed_side_mismatches:negativeControl,total_probes:totalProbes,rows};
await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,JSON.stringify(report,null,2));
console.log(JSON.stringify({samples:rows.length,dynamic_triangles:names.length,total_probes:totalProbes,
 max_boundary_error_px:Math.max(...rows.map(r=>r.max_boundary_error_px)),max_mismatch_distance_px:Math.max(...rows.map(r=>r.max_mismatch_distance_px)),
 mismatched_probes:rows.reduce((s,r)=>s+r.mismatched_probes,0)}));
