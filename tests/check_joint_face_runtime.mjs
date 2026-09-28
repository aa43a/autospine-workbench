// Opt-in official Runtime verification of exported facial controls and reverse seek.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const [folder, coreRoot] = process.argv.slice(2);
const spine = await import(pathToFileURL(path.resolve(coreRoot, 'dist/index.js')));
const pkg = JSON.parse(await fs.readFile(path.join(coreRoot, 'package.json')));
assert.equal(pkg.version, '4.3.13');
const reports = [];
for (const name of ['alice', 'huiye', 'hongmeiling']) {
  const source = JSON.parse(await fs.readFile(path.join(folder, name+'.json')));
  const data = new spine.SkeletonJson(new spine.AtlasAttachmentLoader(new spine.TextureAtlas(source.atlas)))
    .readSkeletonData(source.skeleton);
  const rig = new spine.Skeleton(data), state = new spine.AnimationState(new spine.AnimationStateData(data));
  const entry = state.setAnimation(0, source.animation, false);
  let maximum = 0, probes = 0;
  const seen = new Map();
  for (const row of [...source.samples, ...source.samples.toReversed()]) {
    rig.setupPose(); entry.trackTime = row.time; state.apply(rig); rig.updateWorldTransform(spine.Physics.update);
    const actual = {};
    for (const slot of rig.slots) {
      const attachment = slot.appliedPose.attachment;
      const vertices = new Float32Array(attachment.worldVerticesLength);
      attachment.computeWorldVertices(rig, slot, 0, vertices.length, vertices, 0, 2);
      const expected = row.vertices[slot.data.name];
      assert.equal(vertices.length, expected.length*2);
      for (let i=0; i<expected.length; i++) {
        const delta = Math.hypot(vertices[2*i]-expected[i][0], vertices[2*i+1]-expected[i][1]);
        assert.ok(Number.isFinite(delta) && delta < .001, `${name}/${slot.data.name}/${row.time}: ${delta}`);
        maximum = Math.max(maximum, delta); probes++;
      }
      actual[slot.data.name] = {vertices:Array.from(vertices), alpha:slot.appliedPose.color.a};
      const channel = source.report.channels[slot.data.name];
      if (row.time===.59 && ['white', 'iris'].includes(channel?.role))
        assert.equal(slot.appliedPose.color.a, 0, `${name}/${slot.data.name} must disappear at full blink`);
      if (row.time===.59 && channel?.role==='lash')
        assert.ok(slot.appliedPose.color.a > .99, 'original lash remains as closed line');
    }
    for(const template of source.report.generated_templates || []){
      if([0,1,2].includes(row.time)){
        const opening=row.time===1?1:0;
        assert.equal(actual[template.slot].alpha,opening,'generated interior visibility');
        assert.equal(actual[template.parent_slot].alpha,1-opening,'original mouth complementary visibility');
      }
    }
    if (seen.has(row.time)) assert.deepEqual(actual, seen.get(row.time));
    seen.set(row.time, actual);
  }
  reports.push({name, frames:source.samples.length*2, probes, max_error_px:maximum, passed:true,
    alpha_closure:true, reverse_seek:true, mouth_template_verified:!!source.report.generated_templates?.length,
    capabilities:source.report.inventory.capabilities});
}
const report = {passed:true, runtime_version:pkg.version, export_version:'4.3.26', results:reports,
  scope:'official_core_vertices_alpha_forward_reverse', framebuffer:'not_evaluated', visual_acceptance:'not_evaluated'};
await fs.writeFile(path.join(folder, 'runtime-report.json'), JSON.stringify(report, null, 2));
console.log(JSON.stringify(report));
