import test from 'node:test';
import assert from 'node:assert/strict';
import {poseSelection,POSE_PROFILE} from '../modules/motion-pose-selection.js';
test('pose strategy preserves legacy request and rejects incompatible controls',()=>{
 assert.deepEqual(poseSelection('',{}),{});
 assert.deepEqual(poseSelection(POSE_PROFILE,{clip:null}),{pose_profile:POSE_PROFILE});
 for(const key of ['clip','projection','projection_selection','torso_projection_profile'])
  assert.throws(()=>poseSelection(POSE_PROFILE,{[key]:{}}),/完整片段/);
 assert.throws(()=>poseSelection('unknown',{}));
});
