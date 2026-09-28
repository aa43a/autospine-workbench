// Verify actual exported Spine channels, independent of browser/editor effects.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const [folder, coreRoot] = process.argv.slice(2);
const spine = await import(pathToFileURL(path.resolve(coreRoot, 'dist/index.js')));
const pkg = JSON.parse(await fs.readFile(path.join(coreRoot, 'package.json')));
assert.equal(pkg.version, '4.3.13');
const localFields = ['x','y','rotation','scaleX','scaleY','shearX','shearY'];
const limits = {position:.5, velocity:20, rotation:.25, angularVelocity:15, scale:.01, scaleVelocity:.2, alpha:.01, alphaVelocity:.5};
function evaluator(document, atlas, animation, loop){
  const data = new spine.SkeletonJson(new spine.AtlasAttachmentLoader(new spine.TextureAtlas(atlas))).readSkeletonData(document);
  const rig = new spine.Skeleton(data), state = new spine.AnimationState(new spine.AnimationStateData(data));
  const entry = state.setAnimation(0, animation, loop);
  return {duration:entry.animation.duration, sample(time){
    rig.setupPose(); entry.trackTime = time; state.apply(rig); rig.updateWorldTransform(spine.Physics.update);
    const vertices = {}, alpha = {}, locals = {};
    for(const slot of rig.slots){
      const attachment = slot.appliedPose.attachment;
      if(!attachment) continue;
      const points = new Float32Array(attachment.worldVerticesLength);
      attachment.computeWorldVertices(rig, slot, 0, points.length, points, 0, 2);
      vertices[slot.data.name] = Array.from(points); alpha[slot.data.name] = slot.appliedPose.color.a;
    }
    for(const bone of rig.bones) locals[bone.data.name] = Object.fromEntries(localFields.map(k=>[k,bone.appliedPose[k]]));
    return {vertices,alpha,locals,order:rig.drawOrder.appliedPose.map(s=>s.data.name)};
  }};
}
function seam(values, dt, angular=false){
  let delta = values[3]-values[0]; if(angular) delta = (delta+540)%360-180;
  return {endpoint:Math.abs(delta), velocity:Math.abs((values[3]-values[2])-(values[1]-values[0]))/dt};
}
function bodySeam(frames, dt){
  let position = 0, velocity = 0;
  for(const [slot, points] of Object.entries(frames[0].vertices)){
    for(let i=0;i<points.length;i+=2){
      const x = seam(frames.map(f=>f.vertices[slot][i]),dt), y=seam(frames.map(f=>f.vertices[slot][i+1]),dt);
      position = Math.max(position,Math.hypot(x.endpoint,y.endpoint));
      velocity = Math.max(velocity,Math.hypot(x.velocity,y.velocity));
    }
  }
  return {position_error_px:position,velocity_error_px_per_second:velocity,
    passed:position<=limits.position&&velocity<=limits.velocity};
}
function compareSnapshots(a,b,keys){
  let maximum=0;
  for(const slot of keys){
    assert.equal(a.vertices[slot].length,b.vertices[slot].length);
    for(let i=0;i<a.vertices[slot].length;i++) maximum=Math.max(maximum,Math.abs(a.vertices[slot][i]-b.vertices[slot][i]));
    maximum=Math.max(maximum,Math.abs(a.alpha[slot]-b.alpha[slot]));
  }
  assert.deepEqual(a.order,b.order);
  return maximum;
}
const results=[];
for(const filename of (await fs.readdir(folder)).filter(n=>n.endsWith('.fixture.json')).sort()){
  const fixture=JSON.parse(await fs.readFile(path.join(folder,filename))), name=filename.replace('.fixture.json','');
  const joint=evaluator(fixture.skeleton,fixture.atlas,fixture.animation,false);
  const source=evaluator(fixture.source_skeleton,fixture.atlas,fixture.animation,false);
  let maxError=0,seekError=0,probes=0; const seen=new Map();
  for(const row of [...fixture.samples,...fixture.samples.toReversed()]){
    const actual=joint.sample(row.time);
    for(const [slot,points] of Object.entries(row.vertices)){
      assert.equal(actual.vertices[slot].length,points.length*2);
      for(let i=0;i<points.length;i++){
        const error=Math.hypot(actual.vertices[slot][i*2]-points[i][0],actual.vertices[slot][i*2+1]-points[i][1]);
        assert.ok(Number.isFinite(error)&&error<.001,`${name} ${slot} ${row.time} ${error}`);
        maxError=Math.max(maxError,error); probes++;
      }
    }
    if(seen.has(row.time)) seekError=Math.max(seekError,compareSnapshots(actual,seen.get(row.time),Object.keys(actual.vertices)));
    seen.set(row.time,actual);
  }
  assert.ok(seekError<1e-7,'reverse seek changed a same-time pose');
  const dt=Math.min(1/120,fixture.duration/4), times=[0,dt,fixture.duration-dt,fixture.duration];
  const frames=times.map(t=>joint.sample(t)), body=times.map(t=>source.sample(t));
  const helpers=fixture.loop.added_effects.new_helper_bones, alphaSlots=fixture.loop.added_effects.changed_alpha_slots;
  const helperRows=[],alphaRows=[];
  for(const bone of helpers) for(const field of localFields){
    const values=frames.map(f=>f.locals[bone][field]), metric=seam(values,dt,['rotation','shearX','shearY'].includes(field));
    const angle=['rotation','shearX','shearY'].includes(field),scale=field.startsWith('scale');
    const endpointLimit=angle?limits.rotation:scale?limits.scale:limits.position;
    const velocityLimit=angle?limits.angularVelocity:scale?limits.scaleVelocity:limits.velocity;
    helperRows.push({bone,field,...metric,passed:metric.endpoint<=endpointLimit+1e-5&&metric.velocity<=velocityLimit+.01});
  }
  for(const slot of alphaSlots){
    const values=frames.map(f=>f.alpha[slot]),metric=seam(values,dt), visibilityEqual=(values[0]>=8/255)===(values[3]>=8/255);
    alphaRows.push({slot,...metric,visibility_equal:visibilityEqual,
      passed:metric.endpoint<=limits.alpha+1e-6&&metric.velocity<=limits.alphaVelocity+.001&&visibilityEqual});
  }
  const looped=evaluator(fixture.skeleton,fixture.atlas,fixture.animation,true);
  let repeatedError=0;
  for(const t of [0,dt,looped.duration*.35,looped.duration-dt]){
    const a=looped.sample(t);
    for(const cycle of [1,2]) repeatedError=Math.max(repeatedError,
      compareSnapshots(a,looped.sample(t+cycle*looped.duration),Object.keys(a.vertices)));
  }
  assert.ok(repeatedError<.001,`${name} loop phase drift ${repeatedError}`);
  // Measure both actual wrap crossings; continuity of new local controls is
  // separate from the original body's discontinuity and from world vertices.
  const joins=[];
  for(const cycle of [1,2]){
    const a=looped.sample(cycle*looped.duration-dt),b=looped.sample(cycle*looped.duration),c=looped.sample(cycle*looped.duration+dt);
    let alphaJump=0,visibleEqual=true,helperPassed=true,positionVelocity=0,angleVelocity=0,scaleVelocity=0;
    for(const bone of helpers) for(const field of localFields){
      const velocity=Math.abs((c.locals[bone][field]-b.locals[bone][field])-(b.locals[bone][field]-a.locals[bone][field]))/dt;
      const angle=['rotation','shearX','shearY'].includes(field),scale=field.startsWith('scale');
      if(angle) angleVelocity=Math.max(angleVelocity,velocity);
      else if(scale) scaleVelocity=Math.max(scaleVelocity,velocity);
      else positionVelocity=Math.max(positionVelocity,velocity);
      helperPassed&&=velocity<=(angle?limits.angularVelocity:scale?limits.scaleVelocity:limits.velocity)+.01;
    }
    for(const slot of alphaSlots){alphaJump=Math.max(alphaJump,Math.abs(a.alpha[slot]-b.alpha[slot]),Math.abs(c.alpha[slot]-b.alpha[slot]));
      visibleEqual&&=(a.alpha[slot]>=8/255)===(b.alpha[slot]>=8/255)&&(b.alpha[slot]>=8/255)===(c.alpha[slot]>=8/255);}
    joins.push({cycle,alpha_step_max:alphaJump,visibility_equal:visibleEqual,
      helpers_passed:helperPassed,local_position_velocity_error:positionVelocity,
      local_rotation_velocity_error:angleVelocity,local_scale_velocity_error:scaleVelocity});
  }
  const effectsPassed=helperRows.every(r=>r.passed)&&alphaRows.every(r=>r.passed)&&joins.every(r=>r.helpers_passed&&r.visibility_equal);
  results.push({name,numeric_passed:true,frames:fixture.samples.length*2,probes,max_error_px:maxError,
    reverse_seek_error:seekError,loop_phase_repeat_error:repeatedError,runtime_duration:looped.duration,
    configured_duration:fixture.duration,loop_requested:fixture.loop.requested,
    added_effects:{passed:effectsPassed,helpers:helperRows,alpha:alphaRows,two_wrap_joins:joins},
    source_body:bodySeam(body,dt),overall:bodySeam(frames,dt),
    loop_status:fixture.loop.requested?(effectsPassed&&bodySeam(body,dt).passed&&bodySeam(frames,dt).passed?'passed':'needs_changes'):'not_requested',
    inherited_body_limits_preserved:fixture.loop.source_body.loop_ready===bodySeam(body,dt).passed});
}
const report={profile:'joint-delivery-official-core-v1',runtime_version:pkg.version,results,
  numeric_passed:results.every(r=>r.numeric_passed),
  requested_loop_effects_passed:results.filter(r=>r.loop_requested).every(r=>r.added_effects.passed),
  scope:'official weighted vertices, face alpha, local helpers, forward/reverse seek and two loop wraps',
  framebuffer:'Use independent official WebGL capture; not recaptured by this Core tool.',
  visual_acceptance:'not_evaluated'};
await fs.writeFile(path.join(folder,'official-loop-report.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify({...report,results:results.map(({added_effects,...r})=>({...r,added_effects:{passed:added_effects.passed,two_wrap_joins:added_effects.two_wrap_joins}}))}));
