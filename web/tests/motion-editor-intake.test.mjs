import test from 'node:test';
import assert from 'node:assert/strict';
import {importRequest} from '../modules/motion-editor-intake.js';
test('source upload preserves bytes and explicit NPZ frame convention',()=>{
  const file={name:'动作.NPZ',size:100};const request=importRequest(file,'side',60);
  assert.equal(request.body,file);assert.equal(request.headers['X-Autospine-Npz-Fps'],'60');
  assert.equal(request.headers['X-Autospine-Npz-Profile'],'kimodo-soma77-v1');
  assert.equal(decodeURIComponent(request.headers['X-Autospine-File-Name']),file.name);
  assert.equal(request.headers['X-Autospine-Motion-View'],'side');
  assert.equal(importRequest({name:'a.bvh',size:20},'front',30).headers['X-Autospine-Npz-Fps'],undefined);
});
test('reject unsupported source, oversized upload, and ambiguous NPZ timing',()=>{
  assert.throws(()=>importRequest({name:'a.zip',size:100},'front',30));
  assert.throws(()=>importRequest({name:'a.bvh',size:65*1024*1024},'front',30));
  assert.throws(()=>importRequest({name:'a.npz',size:100},'front',NaN));
});
