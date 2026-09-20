import test from 'node:test';
import assert from 'node:assert/strict';
import {characterProgress,createCharacterProgress} from '../modules/workbench-character-progress.js';
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

test('current incorrect auto audit remains a pending binding despite visual approval',()=>{
 const auto={...job,layers:[{layer_id:'l',state:'rigid_reviewed',binding_decision:{action:'bind',option_id:'rigid:head',decision_source:'policy_auto',evidence_current:true}}]};
 const audit={project_id:'p',job_id:'j',artifact_sha256:'a',authority:'none',review:{reviews:{l:'incorrect'}},metrics:{assessed_bindings:1,eligible_bindings:1,incorrect:1}};
 assert.match(characterProgress(auto,[],null,false,audit)[0],/1 层待处理/);
 assert.match(characterProgress(auto,[],null,false,{...audit,artifact_sha256:'other'})[0],/0 层待处理/);
});

test('default automatic assignments need no individual audit to remain complete',()=>{
 const auto={...job,layers:[{layer_id:'l',state:'rigid_reviewed',binding_decision:{action:'bind',option_id:'rigid:head',decision_source:'policy_auto',evidence_current:true}}]};
 const audit={...job,authority:'none',review:null,metrics:{assessed_bindings:0,eligible_bindings:1,incorrect:0}};
 const rows=characterProgress(auto,[],null,false,audit);
 assert.match(rows[0],/0 层待处理/);assert.match(rows[1],/默认沿用，无需逐项确认/);
});

test('audit shortcut has an explicit action and follows candidate editability',()=>{
 const document={createElement(tag){return {tag,children:[],append(...n){this.children.push(...n);},replaceChildren(...n){this.children=n;},setAttribute(){},addEventListener(k,f){this[k]=f;}};}};
 let opened=0;const ui=createCharacterProgress(document,()=>{},()=>opened++);
 const button=ui.element.children.find(n=>n.textContent==='自动归属与异常修改');
 ui.sync(job,[],null,false);assert.equal(button.disabled,false);button.click();assert.equal(opened,1);
 ui.sync(job,[],null,true);assert.equal(button.disabled,true);
 ui.sync(null,[],null,false);assert.equal(button.disabled,true);
});
