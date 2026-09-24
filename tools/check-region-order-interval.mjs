// Official core draw-order semantics, including reverse seeking and loop wrap.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const [scenePath, reportPath, coreRoot, output] = process.argv.slice(2);
const scene = JSON.parse(await fs.readFile(scenePath));
const report = JSON.parse(await fs.readFile(reportPath));
const pkg = JSON.parse(await fs.readFile(path.join(coreRoot, 'package.json')));
assert.equal(pkg.version, '4.3.13');
const spine = await import(pathToFileURL(path.resolve(coreRoot, 'dist/index.js')));
const data = new spine.SkeletonJson(new spine.AtlasAttachmentLoader(new spine.TextureAtlas(scene.atlas)))
  .readSkeletonData(scene.skeleton);
const skeleton = new spine.Skeleton(data);
const animation = data.findAnimation(report.animation);
const state = new spine.AnimationState(new spine.AnimationStateData(data));
const entry = state.setAnimation(0, report.animation, true);
const [start, end] = report.interval;
const times = [0, start-1e-4, start, start+1e-4, end-1e-4, end, end+1e-4,
  animation.duration, start, 0, end, start, animation.duration+start, animation.duration+end];
for (const time of times) {
  skeleton.setupPose();
  entry.trackTime = time;
  state.apply(skeleton);
  skeleton.updateWorldTransform(spine.Physics.update);
  const local = time % animation.duration;
  const expected = local >= start && local < end ? report.active_order : report.setup_order;
  assert.deepEqual(skeleton.drawOrder.appliedPose.map(slot => slot.data.name), expected);
}
const result = {passed:true, runtime_version:pkg.version, samples:times.length,
  scope:'draw_order_interval_boundaries_reverse_seek_and_loop', framebuffer_status:'not_evaluated'};
await fs.writeFile(output, JSON.stringify(result, null, 2));
console.log(JSON.stringify(result));
