import {test} from 'node:test';
import assert from 'node:assert/strict';
import {solveCamera} from '../modules/motion-camera-solver.js';
function fixture(){
  const bones=[{name:'root',x:0,y:0,rotation:0}];
  for(const side of ['l','r']){
    for(const [name,parent,x,y] of [['upperarm','root',5,15],['forearm','upperarm',10,0],['hand','forearm',8,0],
      ['thigh','root',side==='l'?-4:4,-2],['calf','thigh',0,-10],['foot','calf',0,-8]])
      bones.push({name:`${name}_${side}`,parent:parent==='root'?parent:`${parent}_${side}`,x,y,rotation:0});
  }
  return [{bones,animations:{}},{schema:'autospine.motion-editor-source/v1',precision:12,times:[0,1],duration:1,reference:18,
    role_bones:{'humanoid.arm.upper.left':'upperarm_l'},role_parents:{'humanoid.arm.upper.left':null},
    vectors:{'humanoid.arm.upper.left':[[1,-2,3],[2,-1,3]]},roots:[[0,0,0],[0,0,0]],hip_centers:[[0,0,0],[1,0,0]]}];
}
test('raw solver preserves rig/source and deterministically fits complete timeline',()=>{
  const [rig,source]=fixture(),before=JSON.stringify([rig,source]),keys=[{time:0,yaw:0}];
  const first=solveCamera(rig,source,keys);
  assert.equal(JSON.stringify([rig,source]),before);assert.deepEqual(first,solveCamera(rig,source,keys));
  assert.equal(first.animation.bones.upperarm_l.rotate.length,2);
  assert.equal(first.animation.bones.root.translate[1].x,1);
});
test('unobservable source direction does not invent a fallback rotation',()=>{
  const [rig,source]=fixture();source.vectors['humanoid.arm.upper.left'][0]=[0,0,3];
  assert.throws(()=>solveCamera(rig,source,[{time:0,yaw:0}]),/不可观察/);
});
test('hidden turn between matching endpoints requires denser source sampling',()=>{
  const [rig,source]=fixture();
  assert.throws(()=>solveCamera(rig,source,[{time:0,yaw:0},{time:.5,yaw:360},{time:1,yaw:0}]),/采样/);
});
