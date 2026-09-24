// Official core switch semantics and same-surface refinement regression.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const [sourcePath, candidatePath, reportPath, coreRoot, output] = process.argv.slice(2);
const raw = await Promise.all([sourcePath, candidatePath, reportPath].map(p => fs.readFile(p)));
const [source, candidate, report] = raw.map(r => JSON.parse(r));
const pkg = JSON.parse(await fs.readFile(path.join(coreRoot, 'package.json')));
assert.equal(pkg.version, '4.3.13');
assert.equal(source.atlas, candidate.atlas);
assert.deepEqual(source.textures, candidate.textures);
const spine = await import(pathToFileURL(path.resolve(coreRoot, 'dist/index.js')));
const instances = [source, candidate].map(scene => {
  const data = new spine.SkeletonJson(new spine.AtlasAttachmentLoader(new spine.TextureAtlas(scene.atlas))).readSkeletonData(scene.skeleton);
  const skeleton = new spine.Skeleton(data);
  const state = new spine.AnimationState(new spine.AnimationStateData(data));
  const entry = state.setAnimation(0, report.animation, true);
  return {data, skeleton, state, entry};
});
const duration = instances[0].data.findAnimation(report.animation).duration;
assert.equal(instances[1].data.findAnimation(report.animation).duration, duration);
const [start, end] = report.runtime_interval;
const times = Array.from({length:Math.ceil(duration*120)+1}, (_, i) => Math.min(i/120, duration));
times.push(start-1e-4, start, start+1e-4, end-1e-4, end, end+1e-4,
  start, 0, end, start, duration+end, duration+start);
let maxError = 0, switches = 0;
for (const time of times) {
  const frames = instances.map(({skeleton, state, entry}) => {
    skeleton.setupPose(); entry.trackTime = time; state.apply(skeleton);
    skeleton.updateWorldTransform(spine.Physics.update);
    return skeleton.slots.map(slot => {
      const att = slot.appliedPose.attachment;
      const values = new Float32Array(att.worldVerticesLength);
      att.computeWorldVertices(skeleton, slot, 0, values.length, values, 0, 2);
      return {slot:slot.data.name, name:att.name, values};
    });
  });
  assert.equal(frames[0].length, frames[1].length);
  const active = time%duration >= start && time%duration < end;
  for (let i=0; i<frames[0].length; i++) {
    const a=frames[0][i], b=frames[1][i];
    assert.equal(a.slot, b.slot);
    let expected=Array.from(a.values);
    if (b.slot === report.slot) {
      assert.equal(b.name, active ? report.variant_attachment : report.original_attachment);
      if (active) {
        for (const vertices of report.refinement.added_vertex_sources)
          for (const axis of [0,1]) expected.push(vertices.reduce((s,v)=>s+a.values[2*v+axis],0)/3);
        switches++;
      }
    }
    assert.equal(expected.length, b.values.length);
    for(let j=0;j<expected.length;j++) {
      const error=Math.abs(expected[j]-b.values[j]);
      assert.ok(Number.isFinite(error) && error<.001);
      maxError=Math.max(maxError,error);
    }
  }
}
const result={passed:true,runtime_version:pkg.version,frames:times.length,active_samples:switches,
  max_world_error_px:maxError,input_sha256:raw.map(r=>createHash('sha256').update(r).digest('hex')),
  scope:'same_surface_variant_switch_forward_reverse_loop_not_shape_repair',framebuffer_status:'not_evaluated'};
await fs.writeFile(output,JSON.stringify(result,null,2));
console.log(JSON.stringify(result));
