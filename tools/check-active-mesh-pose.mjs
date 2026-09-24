// Independent official-core comparison of active identities and variable vertices.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const [scenePath, referencePath, coreRoot, output] = process.argv.slice(2);
const raw=await Promise.all([scenePath, referencePath].map(p=>fs.readFile(p)));
const [scene, reference]=raw.map(r=>JSON.parse(r));
const pkg=JSON.parse(await fs.readFile(path.join(coreRoot,'package.json')));
assert.equal(pkg.version,'4.3.13');
const spine=await import(pathToFileURL(path.resolve(coreRoot,'dist/index.js')));
const data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(new spine.TextureAtlas(scene.atlas))).readSkeletonData(scene.skeleton);
const skeleton=new spine.Skeleton(data), state=new spine.AnimationState(new spine.AnimationStateData(data));
const entry=state.setAnimation(0,reference.animation,false);
let error=0, count=0;
for(const frame of [...reference.frames,...reference.frames.slice().reverse()]) {
  skeleton.setupPose();entry.trackTime=frame.time;state.apply(skeleton);
  skeleton.updateWorldTransform(spine.Physics.update);
  assert.deepEqual(skeleton.slots.map(s=>s.data.name).sort(),Object.keys(frame.attachments).sort());
  for(const slot of skeleton.slots) {
    const attachment=slot.appliedPose.attachment;
    assert.equal(attachment?.name??null,frame.attachments[slot.data.name]);
    if(!attachment)continue;
    const points=new Float32Array(attachment.worldVerticesLength);
    attachment.computeWorldVertices(skeleton,slot,0,points.length,points,0,2);
    const expected=frame.vertices[slot.data.name].flat();
    assert.equal(points.length,expected.length);
    for(let i=0;i<points.length;i++) {
      const delta=Math.abs(points[i]-expected[i]);
      assert.ok(Number.isFinite(delta)&&delta<.01,`${slot.data.name} ${frame.time} ${i} ${delta}`);
      error=Math.max(error,delta);
    }
  }
  count++;
}
const result={passed:true,runtime_version:pkg.version,frames:count,max_world_error_px:error,
  input_sha256:raw.map(r=>createHash('sha256').update(r).digest('hex')),
  scope:'active_attachment_and_deform_numeric_forward_reverse',framebuffer_status:'not_evaluated'};
await fs.writeFile(output,JSON.stringify(result,null,2));
console.log(JSON.stringify(result));
