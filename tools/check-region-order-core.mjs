// Official-runtime verification of order-only partition geometry, not visual QA.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const [sourcePath, candidatePath, reportPath, coreRoot, output] = process.argv.slice(2);
const raw = await Promise.all([sourcePath, candidatePath, reportPath].map(p => fs.readFile(p)));
const [source, candidate, report] = raw.map(r => JSON.parse(r));
const pkg = JSON.parse(await fs.readFile(path.join(coreRoot, 'package.json')));
assert.equal(pkg.name, '@esotericsoftware/spine-core');
assert.equal(pkg.version, '4.3.13');
assert.equal(source.atlas, candidate.atlas);
assert.deepEqual(source.textures, candidate.textures);
const spine = await import(pathToFileURL(path.resolve(coreRoot, 'dist/index.js')));
const data = [source, candidate].map(s => new spine.SkeletonJson(
  new spine.AtlasAttachmentLoader(new spine.TextureAtlas(s.atlas))).readSkeletonData(s.skeleton));
assert.deepEqual(data[0].animations.map(a => [a.name,a.duration]), data[1].animations.map(a => [a.name,a.duration]));
const mapping = new Map(report.regions.map(r => [r.slot, r.source_slot]));
let frames = 0, vertices = 0;
function points(data, name, time) {
  const skeleton = new spine.Skeleton(data), state = new spine.AnimationState(new spine.AnimationStateData(data));
  skeleton.setupPose(); state.setAnimation(0, name, false); state.update(time); state.apply(skeleton);
  skeleton.updateWorldTransform(spine.Physics.update);
  return new Map(skeleton.slots.map(slot => {
    const att = slot.appliedPose.attachment;
    const values = new Float32Array(att.worldVerticesLength);
    att.computeWorldVertices(skeleton, slot, 0, values.length, values, 0, 2);
    return [slot.data.name, values];
  }));
}
for (const animation of data[0].animations) {
  const count = Math.ceil(animation.duration * 120);
  for (let i = 0; i <= count; i++) {
    const time = Math.min(i / 120, animation.duration);
    const before = points(data[0], animation.name, time), after = points(data[1], animation.name, time);
    for (const [slot, values] of after) {
      assert.ok(Array.from(values).every(Number.isFinite));
      assert.deepEqual(values, before.get(mapping.get(slot) ?? slot));
      vertices += values.length / 2;
    }
    frames++;
  }
}
const result = {passed:true, runtime_version:pkg.version, frames, vertices,
  input_sha256:raw.map(r => createHash('sha256').update(r).digest('hex')),
  scope:'official_core_world_vertex_identity_at_120hz', framebuffer_status:'not_evaluated', authority:'none'};
await fs.writeFile(output, JSON.stringify(result, null, 2));
console.log(JSON.stringify(result));
