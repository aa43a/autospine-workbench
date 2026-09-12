import test from 'node:test';
import assert from 'node:assert/strict';
import {characterProgress} from '../modules/workbench-character-progress.js';
const job={project_id:'p',job_id:'j',artifact_sha256:'a',status:'needs_review',
 layers:[{layer_id:'l',state:'weighted_candidate',binding_decision:{action:'pending'}}],
 runtime:{geometry_status:'passed',files:{'report.json':'hash'}}};
test('numeric success never fills absent visual decisions',()=>{
 const rows=characterProgress(job);
 assert.match(rows[0],/1 层待处理/);
 assert.match(rows[1],/通过/);
 assert.match(rows[3],/尚未读取/);
});
test('exact visual issues and region confirmation remain separate',()=>{
 const review={...job,authority:'none',review:{aspects:{setup:'acceptable',draw_order:'acceptable',connections:'needs_changes',motion:'not_reviewed'}}};
 const rows=characterProgress(job,['l'],review);
 assert.match(rows[0],/0 层待处理/);
 assert.match(rows[3],/2 \/ 4.*连接/);
 assert.match(characterProgress(job,[],{...review,artifact_sha256:'other'})[3],/尚未读取/);
 assert.match(characterProgress(job,[],review,true)[0],/尚未保存/);
});
