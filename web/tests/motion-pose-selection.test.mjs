import test from 'node:test';
import assert from 'node:assert/strict';
import {poseSelection,POSE_PROFILE,POST_CONTACT_PROFILE,LEGACY_POST_CONTACT_PROFILE} from '../modules/motion-pose-selection.js';
test('pose strategy preserves legacy request and rejects incompatible controls',()=>{
 assert.deepEqual(poseSelection('',{}),{});
 assert.deepEqual(poseSelection(POSE_PROFILE,{clip:null}),{pose_profile:POSE_PROFILE});
 for(const key of ['clip','projection','projection_selection','torso_projection_profile'])
  assert.throws(()=>poseSelection(POSE_PROFILE,{[key]:{}}),/完整片段/);
 assert.throws(()=>poseSelection('unknown',{}));
 assert.deepEqual(poseSelection(POST_CONTACT_PROFILE,{}),{pose_profile:POST_CONTACT_PROFILE});
 assert.throws(()=>poseSelection(POST_CONTACT_PROFILE,{contact_correction:false}),/接触/);
 assert.notEqual(POST_CONTACT_PROFILE,LEGACY_POST_CONTACT_PROFILE);
 assert.deepEqual(poseSelection(LEGACY_POST_CONTACT_PROFILE,{}),{pose_profile:LEGACY_POST_CONTACT_PROFILE});
});
