import test from 'node:test';
import assert from 'node:assert/strict';
import {createCharacterLedger,auditBindingExceptions} from '../modules/workbench-character-ledger.js';
import {characterProgress} from '../modules/workbench-character-progress.js';
const all=n=>[n,...n.children.flatMap(all)];
const document={createElement(tag){return {tag,children:[],append(...n){this.children.push(...n);},replaceChildren(...n){this.children=n;},setAttribute(){},addEventListener(name,fn){this[name]=fn;}};}};
const layer={layer_id:'eye',name:'眼睛',state:'rigid_reviewed',regions:[],binding_decision:{action:'bind',option_id:'rigid:head',decision_source:'policy_auto',evidence_current:true}};
const job={project_id:'p',job_id:'j',artifact_sha256:'a',status:'needs_review',layers:[layer]};
const audit={project_id:'p',job_id:'j',artifact_sha256:'a',authority:'none',review:{reviews:{eye:'incorrect'}},metrics:{assessed_bindings:1,eligible_bindings:1,incorrect:1}};

test('incorrect current automatic binding appears in pending ledger and can be located',()=>{
 const located=[];const ui=createCharacterLedger(document,{locate:r=>located.push(r)});
 const before=structuredClone(job);
 ui.sync({projectId:'p',job,audit,confirmedLayerIds:['eye'],disabled:false});
 assert.match(all(ui.element).find(n=>n.tag==='summary').textContent,/待处理 1/);
 assert.ok(all(ui.element).some(n=>n.textContent.includes('已有视觉接受不能消除此异常')));
 all(ui.element).find(n=>n.tag==='button').click();
 assert.deepEqual(located,[{layer_id:'eye',type:'binding'}]);
 assert.match(characterProgress(job,['eye'],null,false,audit)[0],/1 层待处理/);
 assert.deepEqual(job,before);
 ui.sync({projectId:'p',job,audit:{...audit,review:{reviews:{eye:'correct'}}},disabled:false});
 assert.match(all(ui.element).find(n=>n.tag==='summary').textContent,/待处理 0/);
});

test('stale, foreign, and nonautomatic audit rows cannot create exceptions',()=>{
 for(const changed of [{artifact_sha256:'old'},{project_id:'q'},{job_id:'old'},{authority:'release'}]){
  assert.equal(auditBindingExceptions(job,{...audit,...changed}).size,0);
 }
 for(const verdict of ['not_reviewed','unobservable','correct'])assert.equal(auditBindingExceptions(job,{...audit,review:{reviews:{eye:verdict}}}).size,0);
 assert.equal(auditBindingExceptions({...job,layers:[{...layer,binding_decision:{...layer.binding_decision,decision_source:'explicit_selection'}}]},audit).size,0);
 assert.equal(auditBindingExceptions(job,{...audit,review:{reviews:{unknown:'incorrect'}}}).size,0);
});
