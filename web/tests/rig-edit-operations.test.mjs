import {test} from 'node:test';
import assert from 'node:assert/strict';
import {applyRigEditOperations as apply,layerEditImpact} from '../modules/rig-edit-operations.js';
import {validateEditorDraft} from '../modules/motion-editor-draft.js';
import {editorBuildRequest} from '../modules/motion-editor-build.js';
const layers=[{slot:'arm',supported:true},{slot:'hat',supported:false}];
const options={layers};
test('late failure rolls back whole batch and identifies property; input is untouched',()=>{
  const source=apply(null,[{op:'transform',slot:'arm',values:{dx:3}}],options).value;
  const before=structuredClone(source);
  const result=apply(source,[{op:'transform',slot:'arm',values:{dx:9}},
    {op:'transform',slot:'arm',values:{scaleX:0}}],options);
  assert.equal(result.ok,false);assert.deepEqual(result.value,before);assert.deepEqual(source,before);
  assert.equal(result.diagnostics[0].path,'/layers/arm/scaleX');
  assert.equal(result.diagnostics[0].operation,1);
});
test('inverse restores edits and order exactly, without sharing mutable state',()=>{
  const before=apply(null,[{op:'transform',slot:'arm',values:{dx:3}}],options).value;
  const result=apply(before,[{op:'transform',slot:'arm',values:{rotation:30}},
    {op:'order',slots:['hat','arm']}],options);
  assert.equal(result.ok,true);
  assert.deepEqual(apply(result.value,result.inverse,options).value,before);
  result.value.transforms[0].dx=55;assert.equal(before.transforms[0].dx,3);
});
test('unsupported, unknown, malformed operations never silently apply',()=>{
  for(const operations of [[{op:'transform',slot:'hat',values:{dx:2}}],
    [{op:'reset',slot:'missing'}],[{op:'order',slots:['arm']}],
    [{op:'transform',slot:'arm',values:{dx:NaN}}],[{op:'delete',slot:'arm'}]]){
    assert.equal(apply(null,operations,options).ok,false);
  }
});
test('same transaction snapshot survives draft serialization and both build routes',()=>{
  const result=apply(null,[{op:'transform',slot:'arm',values:{dx:3,rotation:20,scaleY:1.2}},
    {op:'order',slots:['hat','arm']}],options);
  for(const yaw of [30,180]){
    const draft=validateEditorDraft(JSON.parse(JSON.stringify({schema:'autospine.motion-editor-draft/v1',
      project_id:'alice',character_job_id:'job-1',source_id:'motion-1',duration:2,time:1,
      keys:[{time:0,yaw}],layer_edits:result.value})));
    assert.deepEqual(editorBuildRequest(draft).layer_edits,result.value);
  }
});
test('scope reports review dependencies, never pretends cache reuse',()=>{
  const result=apply(null,[{op:'order',slots:['hat','arm']}],options);
  assert.deepEqual(result.impact.checks,['occlusion','runtime']);
  assert.equal(result.impact.execution,'full_build');
  assert.deepEqual(layerEditImpact(null).checks,[]);
});
