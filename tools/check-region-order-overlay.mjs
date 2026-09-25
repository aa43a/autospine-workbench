// Check composed orders against independently played source Runtime timelines.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const [sourcePath,candidatePath,reportPath,coreRoot,output]=process.argv.slice(2);
const raws=await Promise.all([sourcePath,candidatePath,reportPath].map(p=>fs.readFile(p)));
const [source,candidate,report]=raws.map(r=>JSON.parse(r));
const pkg=JSON.parse(await fs.readFile(path.join(coreRoot,'package.json')));
assert.equal(pkg.name,'@esotericsoftware/spine-core');assert.equal(pkg.version,'4.3.13');
assert.equal(source.atlas,candidate.atlas);assert.deepEqual(source.textures,candidate.textures);
const spine=await import(pathToFileURL(path.resolve(coreRoot,'dist/index.js')));
function load(scene){return new spine.SkeletonJson(new spine.AtlasAttachmentLoader(new spine.TextureAtlas(scene.atlas))).readSkeletonData(scene.skeleton);}
const before=load(source),after=load(candidate);
assert.deepEqual(before.animations.map(a=>[a.name,a.duration]),after.animations.map(a=>[a.name,a.duration]));
const groups=new Map(),mapping=new Map(),selected=new Set();
for(const r of report.regions){
  if(!groups.has(r.source_slot))groups.set(r.source_slot,[]);
  groups.get(r.source_slot).push(r.slot);mapping.set(r.slot,r);
  if(r.group==='selected')selected.add(r.slot);
}
assert.ok(selected.size);let samples=0,vertices=0;
for(const animation of before.animations){
  const duration=animation.duration;assert.ok(duration>0);
  const keys=source.skeleton.animations[animation.name].drawOrder??[];
  const boundaries=[0,duration,...keys.map(k=>Math.fround(k.time??0)),...report.runtime_interval];
  const ascending=[...new Set([...Array.from({length:Math.ceil(duration*120)+1},(_,i)=>Math.min(i/120,duration)),
    ...boundaries.flatMap(t=>[t-1e-5,t,t+1e-5]).filter(t=>t>=0&&t<=duration)])].sort((a,b)=>a-b);
  for(const loop of [false,true]){
    const rigs=[before,after].map(data=>{
      const skeleton=new spine.Skeleton(data),state=new spine.AnimationState(new spine.AnimationStateData(data));
      return {skeleton,state,entry:state.setAnimation(0,animation.name,loop)};
    });
    const times=[...ascending,...ascending.toReversed(),...(loop?ascending.map(t=>t+duration):[])];
    for(const time of times){
      for(const rig of rigs){rig.skeleton.setupPose();rig.entry.trackTime=time;rig.state.apply(rig.skeleton);rig.skeleton.updateWorldTransform(spine.Physics.update);}
      const [a,b]=rigs.map(r=>r.skeleton);
      let expected=a.drawOrder.appliedPose.flatMap(s=>groups.get(s.data.name)??[s.data.name]);
      const local=loop?time%duration:Math.min(time,duration),[start,end]=report.runtime_interval;
      if(animation.name===report.animation&&local>=start&&local<end){
        const moved=expected.filter(n=>selected.has(n));expected=expected.filter(n=>!selected.has(n));
        const index=expected.indexOf(report.reference_slot);assert.ok(index>=0);
        expected.splice(index+(report.side==='after'?1:0),0,...moved);
      }
      assert.deepEqual(b.drawOrder.appliedPose.map(s=>s.data.name),expected,`${animation.name} loop=${loop} time=${time}`);
      function points(skeleton,slot){const mesh=slot.appliedPose.attachment,values=new Float32Array(mesh.worldVerticesLength);
        mesh.computeWorldVertices(skeleton,slot,0,values.length,values,0,2);return values;}
      const sourcePoints=new Map(a.slots.map(s=>[s.data.name,points(a,s)]));
      for(const slot of b.slots){
        const region=mapping.get(slot.data.name),actual=points(b,slot);
        let expectedPoints=sourcePoints.get(region?.source_slot??slot.data.name);
        if(region?.source_vertex_indices)expectedPoints=new Float32Array(region.source_vertex_indices.flatMap(i=>[expectedPoints[2*i],expectedPoints[2*i+1]]));
        assert.ok(Array.from(actual).every(Number.isFinite));assert.deepEqual(actual,expectedPoints);vertices+=actual.length/2;
      }
      samples++;
    }
  }
}
const result={passed:true,runtime_version:pkg.version,samples,vertices,
  input_sha256:raws.map(r=>createHash('sha256').update(r).digest('hex')),
  scope:'source_runtime_order_composition_and_vertex_identity_forward_reverse_loop',
  framebuffer_status:'not_evaluated',visual_acceptance:'not_evaluated',authority:'none'};
await fs.writeFile(output,JSON.stringify(result,null,2));console.log(JSON.stringify(result));
