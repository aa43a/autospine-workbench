// Official Runtime material coordinates; no framebuffer or floor-contact claim.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const [folder,reportPath,coreRoot,output]=process.argv.slice(2);
const hash=b=>createHash('sha256').update(b).digest('hex');
const canonical=v=>v===null||typeof v!=='object'?JSON.stringify(v):Array.isArray(v)?'['+v.map(canonical).join(',')+']':'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';
const rawReport=await fs.readFile(reportPath),report=JSON.parse(rawReport);
const inventory=JSON.parse(await fs.readFile(path.join(folder,'inventory.json')));
assert.equal(hash(canonical(inventory)),report.artifact_sha256);
const files=new Map();
for(const [name,digest] of Object.entries(inventory)){
  assert.ok(/^[a-zA-Z0-9_./-]+$/.test(name)&&!name.split('/').some(p=>!p||p==='.'||p==='..'));
  const raw=await fs.readFile(path.join(folder,name));assert.equal(hash(raw),digest);files.set(name,raw);
}
assert.equal(hash(files.get('skeleton.json')),report.skeleton_byte_sha256);
const doc=JSON.parse(files.get('skeleton.json'));
assert.equal(doc.skeleton.spine,'4.3.26');
const pkg=JSON.parse(await fs.readFile(path.join(coreRoot,'package.json')));assert.equal(pkg.version,'4.3.13');
const spine=await import(pathToFileURL(path.resolve(coreRoot,'dist/index.js')));
const data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(new spine.TextureAtlas(files.get('skeleton.atlas').toString()))).readSkeletonData(doc);
const skeleton=new spine.Skeleton(data),state=new spine.AnimationState(new spine.AnimationStateData(data));
const entry=state.setAnimation(0,report.request.animation,false);
for(const a of report.request.anchors)assert.equal(hash(files.get(a.texture_path)),a.texture_sha256);
function locate(query,uv,tri,world){
  const hits=[];
  for(let i=0;i<tri.length;i+=3){
    const [a,b,c]=tri.slice(i,i+3),ax=uv[2*a],ay=uv[2*a+1];
    const bx=uv[2*b]-ax,by=uv[2*b+1]-ay,cx=uv[2*c]-ax,cy=uv[2*c+1]-ay;
    const det=bx*cy-by*cx;if(Math.abs(det)<1e-14)continue;
    const dx=query[0]-ax,dy=query[1]-ay,v=(dx*cy-dy*cx)/det,w=(bx*dy-by*dx)/det,u=1-v-w;
    if(Math.min(u,v,w)<-1e-8)continue;
    const point=[0,1].map(k=>u*world[2*a+k]+v*world[2*b+k]+w*world[2*c+k]);
    if(!hits.some(p=>Math.hypot(p[0]-point[0],p[1]-point[1])<=1e-5))hits.push(point);
  }
  return hits;
}
const rows=new Map(report.records.map(r=>[r.id,r]));
assert.equal(rows.size,report.request.anchors.length);
let maximum=0,checks=0;const origins=new Map(),observed=[];
const times=report.request.times;
for(const index of [...times.keys(),...Array.from(times.keys()).reverse()]){
  const time=times[index];skeleton.setupPose();entry.trackTime=time;state.apply(skeleton);skeleton.updateWorldTransform(spine.Physics.update);
  for(const anchor of report.request.anchors){
    const expected=rows.get(anchor.id).samples[index];assert.equal(expected.time,time);
    // A partly unresolved CPU result cannot become a successful Runtime proof.
    assert.equal(expected.status,'measured');
    const slot=skeleton.findSlot(anchor.slot),attachment=slot.appliedPose.attachment;
    assert.equal(attachment?.name,expected.attachment);
    assert.equal('images/'+attachment.path+'.png',anchor.texture_path);
    const world=new Float32Array(attachment.worldVerticesLength);
    attachment.computeWorldVertices(skeleton,slot,0,world.length,world,0,2);
    const hits=locate(anchor.uv,attachment.regionUVs,attachment.triangles,world);assert.equal(hits.length,1);
    const point=hits[0],error=Math.hypot(point[0]-expected.world[0],point[1]-expected.world[1]);
    assert.ok(Number.isFinite(error)&&error<.01,`${anchor.id} ${time} material error ${error}`);
    if(index===0&&!origins.has(anchor.id))origins.set(anchor.id,point);
    const origin=origins.get(anchor.id),drift=Math.hypot(point[0]-origin[0],point[1]-origin[1]);
    assert.ok(Math.abs(drift-expected.drift_px)<.02);
    maximum=Math.max(maximum,error);checks++;
    observed.push({id:anchor.id,time,attachment:attachment.name,world:point,drift_px:drift});
  }
}
const result={passed:true,runtime_version:pkg.version,target_version:doc.skeleton.spine,
  artifact_sha256:report.artifact_sha256,input_report_sha256:hash(rawReport),checks,
  maximum_world_error_px:maximum,observed,scope:'official_core_material_numeric_forward_reverse',
  contact_acceptance:'not_evaluated',framebuffer_status:'not_evaluated'};
await fs.writeFile(output,JSON.stringify(result,null,2),{flag:'wx'});
console.log(JSON.stringify({...result,observed:undefined}));
