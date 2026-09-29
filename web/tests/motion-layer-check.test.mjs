import {test} from 'node:test';
import assert from 'node:assert/strict';
import {checkLayerDraft,editCheckSignature} from '../modules/motion-layer-check.js';
const draft={source_id:'motion-source',project_id:'alice',character_job_id:'job-1',time:0};
test('checks exact identity and result; playback time does not invalidate preflight',async()=>{
  let payload;
  const result=await checkLayerDraft(draft,async(url,body)=>{
    assert.equal(url,'/api/motions/motion-source/layer-edit-check');payload=body;
    return {ok:true,value:body.operations[0].value,receipt_sha256:'a'.repeat(64)};
  });
  assert.equal(payload.character_job_id,'job-1');assert.equal(result.receipt_sha256,'a'.repeat(64));
  assert.equal(editCheckSignature(draft),editCheckSignature({...draft,time:1}));
  assert.notEqual(editCheckSignature(draft),editCheckSignature({...draft,character_job_id:'job-2'}));
});
test('server rejection and mismatched snapshot never become a build receipt',async()=>{
  await assert.rejects(checkLayerDraft(draft,async()=>({ok:false,diagnostics:[{slot:'arm',path:'/scaleX',code:'invalid',hint:'retry'}]})),/arm/);
  await assert.rejects(checkLayerDraft(draft,async()=>({ok:true,receipt_sha256:'a'.repeat(64),value:{profile:'slot-world-affine-v1',transforms:[],draw_order:['other']}})),/不一致/);
});
