// Check actual official alpha timelines, separate from world-vertex agreement.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const [folder,coreRoot,output]=process.argv.slice(2);
const spine=await import(pathToFileURL(path.resolve(coreRoot,'dist/index.js')));
const pkg=JSON.parse(await fs.readFile(path.join(coreRoot,'package.json')));assert.equal(pkg.version,'4.3.13');
const doc=JSON.parse(await fs.readFile(path.join(folder,'skeleton.json'))),atlas=new spine.TextureAtlas(await fs.readFile(path.join(folder,'skeleton.atlas'),'utf8'));
const repair=JSON.parse(await fs.readFile(path.join(folder,'motion-repair.json'))),m=repair.material;
const data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(doc);
const [start,end]=m.interval,times=[0,start-1e-4,start,start+1e-4,(start+end)/2,end-1e-4,end,end+1e-4].filter(t=>t>=0);
const rows=[];
for(const time of times){
 const skeleton=new spine.Skeleton(data),state=new spine.AnimationState(new spine.AnimationStateData(data));
 skeleton.setupPose();state.setAnimation(0,repair.animation,false);state.update(time);state.apply(skeleton);
 const original=skeleton.findSlot(m.original_region_slot).pose.color.a,replacement=skeleton.findSlot(m.replacement_slot).pose.color.a;
 const expected=start<=time&&time<end?1:0;assert.equal(replacement,expected);assert.equal(original,1-expected);
 rows.push({time,original,replacement});
}
await fs.writeFile(output,JSON.stringify({passed:true,runtime:pkg.version,scope:'official_alpha_timeline_not_raster_acceptance',rows}));
console.log(JSON.stringify({passed:true,samples:rows.length}));
