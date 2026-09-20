import test from 'node:test';
import assert from 'node:assert/strict';
import {createAutoBindingAudit} from '../modules/workbench-character-auto-audit.js';
const all=n=>[n,...n.children.flatMap(all)];
const document={createElement(tag){return {tag,children:[],append(...n){this.children.push(...n);},replaceChildren(...n){this.children=n;},setAttribute(){}};}};
const job={project_id:'p',job_id:'j',artifact_sha256:'a'};
const response={...job,authority:'none',inventory:[{layer_id:'eye',name:'眼睛',option_id:'rigid:head'}],review:null,review_sha256:null,
 metrics:{assessed_bindings:0,eligible_bindings:1,incorrect:0,unobservable:0,sampled_error_rate:null}};
test('unreviewed default, explicit judgment only, one source-bound save',async()=>{
 const posts=[],located=[];const ui=createAutoBindingAudit(document,{locate:row=>located.push(row),apiRequest:async(_url,init)=>{if(init.method==='POST')posts.push(JSON.parse(init.body));return response;}});
 ui.sync(job,true);await ui.request();
 const select=all(ui.element).find(n=>n.tag==='select');assert.equal(select.value,'not_reviewed');
 all(ui.element).find(n=>n.textContent==='定位图层').onclick();assert.deepEqual(located,[{layer_id:'eye',type:'binding'}]);
 await ui.request(true);assert.equal(posts.length,0);
 select.value='incorrect';select.onchange();await ui.request(true);
 assert.deepEqual(posts,[{expected_artifact_sha256:'a',expected_review_sha256:null,reviews:{eye:'incorrect'}}]);
 ui.dispose();
});
test('dirty state and candidate change block stale audit writes',async()=>{
 let release,calls=0;const ui=createAutoBindingAudit(document,{apiRequest:()=>{calls++;return new Promise(r=>release=r);}});
 ui.sync(job,false);await ui.request();assert.equal(calls,0);
 ui.sync(job,true);const pending=ui.request();ui.sync(null,false);release(response);await pending;
 await ui.request(true);assert.equal(calls,1);ui.dispose();
});

test('restored audit loads once, exposes saved exceptions, and never writes',async()=>{
 let calls=0,changed=0;
 const saved={...response,review:{reviews:{eye:'incorrect'}},metrics:{...response.metrics,incorrect:1,assessed_bindings:1,sampled_error_rate:1}};
 const ui=createAutoBindingAudit(document,{changed:()=>changed++,apiRequest:async(_url,init)=>{calls++;assert.equal(init.method,undefined);return saved;}});
 ui.sync(job,true);const pending=ui.ensureLoaded();ui.ensureLoaded();await pending;
 assert.equal(calls,1);assert.equal(changed,1);assert.equal(ui.element.open,true);assert.equal(ui.current(),saved);
 ui.sync(job,true);await ui.ensureLoaded();assert.equal(calls,1);
 ui.sync({...job,artifact_sha256:'new'},true);assert.equal(ui.current(),null);assert.equal(ui.element.open,false);
 await ui.ensureLoaded();assert.equal(calls,2);assert.equal(ui.current(),null);
 await ui.ensureLoaded();assert.equal(calls,2);ui.dispose();
});

test('failed background read waits for manual retry and deferred reads respect dirty state',async()=>{
 let calls=0;
 const ui=createAutoBindingAudit(document,{apiRequest:async()=>{calls++;if(calls===1)throw Error('offline');return response;}});
 ui.sync(job,true);const delayed=ui.ensureLoaded();ui.sync(job,false);await delayed;assert.equal(calls,0);
 ui.sync(job,true);await ui.ensureLoaded();assert.equal(calls,1);
 await ui.ensureLoaded();assert.equal(calls,1);
 await ui.request();assert.equal(calls,2);assert.equal(ui.current(),response);ui.dispose();
});

test('project changes or disposal cancel queued automatic reads',async()=>{
 let calls=0;const ui=createAutoBindingAudit(document,{apiRequest:async()=>{calls++;return response;}});
 ui.sync(job,true);const pending=ui.ensureLoaded();ui.sync(null,false);await pending;assert.equal(calls,0);
 ui.sync(job,true);const disposed=ui.ensureLoaded();ui.dispose();await disposed;assert.equal(calls,0);
});
