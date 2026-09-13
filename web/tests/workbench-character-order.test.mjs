import test from 'node:test';
import assert from 'node:assert/strict';
import {createCharacterOrder} from '../modules/workbench-character-order.js';
const document={createElement(tag){return {tag,children:[],setAttribute(){},append(...n){this.children.push(...n);},replaceChildren(...n){this.children=n;}};}};
const all=n=>[n,...n.children.flatMap(all)];
const job={job_id:'job',artifact_sha256:'a'.repeat(64),layers:[{name:'裙',regions:[{region_id:'skirt'}]},{name:'腿',regions:[{region_id:'leg'}]}]};
test('only explicit selected pairs are saved; new artifact resets draft',()=>{
 const calls=[],view=createCharacterOrder(document,b=>calls.push(b));view.sync(job,null,false);
 const select=all(view.element).filter(n=>n.tag==='select');select[0].value='leg';select[1].value='skirt';select[1].onchange();
 all(view.element).find(n=>n.textContent==='添加遮挡关系').onclick();
 const button=all(view.element).find(n=>n.textContent==='确认并保存遮挡关系');assert.equal(button.disabled,false);button.onclick();
 assert.deepEqual(calls,[{action:'replace',job_id:'job',expected_artifact_sha256:job.artifact_sha256,constraints:[['leg','skirt']]}]);
 view.sync({...job,artifact_sha256:'b'.repeat(64)},null,false);
 assert.equal(all(view.element).find(n=>n.textContent==='确认并保存遮挡关系').disabled,true);
});
test('stale candidate still permits explicit revoke; dirty state disables it',()=>{
 const calls=[],view=createCharacterOrder(document,b=>calls.push(b)),state={active:true,review:{constraints:[['leg','skirt']]}};
 view.sync(null,state,true);assert.equal(all(view.element).find(n=>n.tag==='button').disabled,true);
 view.sync(null,state,false);all(view.element).find(n=>n.tag==='button').onclick();assert.deepEqual(calls,[{action:'revoke'}]);
});
