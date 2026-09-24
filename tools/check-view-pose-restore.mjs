import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const load=async file=>import('data:text/javascript;base64,'+Buffer.from(await fs.readFile(new URL('../web/modules/'+file,import.meta.url),'utf8')).toString('base64'));
const {restoreViewDraft,bindViewTexture}=await load('view-pose-restore.js');
const {createViewState}=await load('view-pose-state.js');
const live={request:{job_id:'one',draft_revision:1},view_pose:{document_sha256:'doc',slot:'arm',animation:'reach',interval:[0,4],poses:[]},control_template:{mesh_sha256:'mesh',source_uv:[[0,0],[1,0],[0,1]],target_uv:[[0,0],[1,0],[0,1]],target_xy:[[0,0],[10,0],[0,10]],triangles:[[0,1,2]]}};
const state=createViewState(live);state.move('uv',1,[.9,0]);state.move('pose',1,[12,0]);state.save(1,0,2);state.move('pose',1,[14,0]);state.save(1.5,0,2);
const saved=JSON.parse(JSON.stringify(state.export())),before=structuredClone(saved),restored=restoreViewDraft(live,saved);
assert.deepEqual(restored.control_template.target_xy[1],[14,0]);assert.deepEqual(restored.control_template.target_uv[1],[.9,0]);
assert.deepEqual(restored.view_pose.poses,saved.view_pose.poses);assert.deepEqual(saved,before);
const resumed=createViewState(restored,live.view_pose.interval[1]);resumed.save(3,0,4);assert.equal(resumed.export().view_pose.poses.length,3);
for(const mutate of [v=>v.request.draft_revision++,v=>v.view_pose.document_sha256='changed',v=>v.view_pose.interval=[0,5],v=>v.view_pose.poses[1].time=1,v=>v.view_pose.poses[0].correspondence.source_uv[0][0]=.2,v=>v.view_pose.poses[0].correspondence.target_uv[0][0]=.2,v=>v.view_pose.poses[0].correspondence.target_xy[0]=[null,1]]){
  const bad=structuredClone(saved);mutate(bad);assert.throws(()=>restoreViewDraft(live,bad));
}
bindViewTexture(restored,'png',[100,200]);bindViewTexture(restored,'png',[100,200]);
assert.throws(()=>bindViewTexture(restored,'changed',[100,200]),/不一致/);
assert.throws(()=>bindViewTexture(restored,'png',[200,100]),/不一致/);
console.log('Restore round trip, source identity, topology, times, shared UV and texture identity checks passed');
