import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DRAFT_SCHEMA,validateEditorDraft,matchEditorDraft} from '../modules/motion-editor-draft.js';
const draft=()=>({schema:DRAFT_SCHEMA,project_id:'alice',character_job_id:'job-1',source_id:'motion-1',
  duration:2,time:1,keys:[{time:0,yaw:350},{time:2,yaw:710}]});
test('round trip preserves turns and detaches mutable keys',()=>{
  const original=draft(),value=matchEditorDraft(JSON.parse(JSON.stringify(original)),original);
  assert.deepEqual(value,original);value.keys[0].yaw=0;assert.equal(original.keys[0].yaw,350);
});
test('sampling version is retained; old drafts stay unchanged',()=>{
  const value={...draft(),sampling_profile:'camera-world-linear-adaptive-v1'};
  assert.deepEqual(validateEditorDraft(value),value);
  const projected={...value,sampling_profile:'camera-world-projected-adaptive-v2'};
  assert.deepEqual(matchEditorDraft(JSON.parse(JSON.stringify(projected)),value),projected);
  assert.equal(validateEditorDraft(draft()).sampling_profile,undefined);
  assert.throws(()=>validateEditorDraft({...value,sampling_profile:'future'}));
});
test('restoring refuses changed target job, source, project and duration',()=>{
  for(const field of ['character_job_id','source_id','project_id','duration'])
    assert.throws(()=>matchEditorDraft(draft(),{...draft(),[field]:field==='duration'?3:'other'}));
});
test('untrusted imports cannot add paths, invalid positions or malformed tracks',()=>{
  for(const value of [{...draft(),path:'x'},{...draft(),project_id:'../alice'},
    {...draft(),time:3},{...draft(),keys:[{time:0,yaw:Infinity}]},{...draft(),schema:'other'}])
    assert.throws(()=>validateEditorDraft(value));
});
