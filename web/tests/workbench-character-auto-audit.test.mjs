import test from 'node:test';
import assert from 'node:assert/strict';
import {createAutoBindingAudit} from '../modules/workbench-character-auto-audit.js';
const all=n=>[n,...n.children.flatMap(all)];
const document={createElement(tag){return {tag,children:[],append(...n){this.children.push(...n);},replaceChildren(...n){this.children=n;},setAttribute(){},addEventListener(event,fn){this['on'+event]=fn;}};}};
const job={project_id:'p',job_id:'j',artifact_sha256:'a'};
const response={...job,authority:'none',inventory:[{layer_id:'eye',name:'眼睛',option_id:'rigid:head'}],review:null,review_sha256:null,
 metrics:{assessed_bindings:0,eligible_bindings:1,incorrect:0,unobservable:0,sampled_error_rate:null}};
test('carried error is visible without copying verdict and time-only save retains it',async()=>{
 let now=0,posted;
 const value={...response,exception_sha256:'proof',exception_continuity:{exceptions:[{layer_id:'eye',source_job_id:'job-old'}]},metrics:{...response.metrics,carried_exception_layers:1}};
 const ui=createAutoBindingAudit(document,{clock:()=>now,apiRequest:async(url,init)=>{
  if(init.method==='POST')posted=JSON.parse(init.body);return value;
 }});
 ui.sync(job,true);await ui.request();
 assert.equal(ui.element.open,true);
 assert.equal(all(ui.element).find(n=>n.tag==='select').value,'incorrect');
 assert.ok(all(ui.element).some(n=>n.textContent.includes('未修复异常沿用自 job-old')));
 all(ui.element).find(n=>n.textContent==='开始 / 继续复核计时').onclick();now=5000;await ui.request(true);
 assert.deepEqual(posted.reviews,{});assert.equal(posted.expected_exception_sha256,'proof');ui.dispose();
});
test('exception edit saves the exact exception before opening binding editor; failure retains draft',async()=>{
 let fail=true;const events=[];
 const ui=createAutoBindingAudit(document,{locate:row=>events.push(row),apiRequest:async(url,init)=>{
  if(init.method==='POST'){events.push(JSON.parse(init.body));if(fail)throw Error('offline');return {...response,review:{reviews:{eye:'incorrect'}}};}return response;
 }});
 ui.sync(job,true);await ui.request();
 const modify=()=>all(ui.element).find(n=>n.textContent==='标记异常并修改');
 await modify().onclick();assert.equal(events.length,1);
 assert.equal(all(ui.element).find(n=>n.tag==='select').value,'incorrect');
 fail=false;await modify().onclick();
 assert.deepEqual(events[1],{expected_artifact_sha256:'a',expected_review_sha256:null,reviews:{eye:'incorrect'}});
 assert.deepEqual(events[2],{layer_id:'eye',type:'binding'});ui.dispose();
});
test('save-next retains failed draft and advances only after successful save',async()=>{
 let fail=true,posted;
 const value={...response,inventory:[...response.inventory,{layer_id:'neck',name:'颈部',option_id:'rigid:neck'}]};
 const ui=createAutoBindingAudit(document,{apiRequest:async(url,init)=>{if(init.method==='POST'){posted=JSON.parse(init.body);if(fail)throw Error('offline');return {...value,review:{reviews:posted.reviews}};}return value;}});
 ui.sync(job,true);await ui.request();
 const button=text=>all(ui.element).find(n=>n.textContent===text);
 button('当前项：归属正确').onclick();await button('保存并下一项').onclick();
 assert.equal(all(ui.element).filter(n=>n.tag==='select')[0].value,'correct');
 assert.ok(all(ui.element).some(n=>n.textContent==='当前 1 / 2 · 1 项尚未保存'));
 fail=false;await button('保存并下一项').onclick();
 assert.ok(all(ui.element).some(n=>n.textContent==='当前 2 / 2 · 0 项尚未保存'));
 assert.deepEqual(posted.reviews,{eye:'correct'});ui.dispose();
});
test('explicit audit stopwatch can save time without inventing an assessed verdict',async()=>{
 let now=0,post;
 const ui=createAutoBindingAudit(document,{clock:()=>now,apiRequest:async(url,init)=>{if(init.method==='POST'){post=JSON.parse(init.body);return {...response,review:{reviews:post.reviews,timing:post.timing}};}return response;}});
 ui.sync(job,true);await ui.request();
 all(ui.element).find(n=>n.textContent==='开始 / 继续复核计时').onclick();
 now=12000;await ui.request(true);
 assert.deepEqual(post.reviews,{eye:'not_reviewed'});
 assert.equal(post.timing.scope,'automatic_binding_audit_session');assert.equal(post.timing.seconds,12);
 ui.sync({...job,artifact_sha256:'other'},true);assert.ok(all(ui.element).some(n=>n.textContent?.startsWith('尚未计时。')));ui.dispose();
});
test('unreviewed default, explicit judgment only, one source-bound save',async()=>{
 const posts=[],located=[];const ui=createAutoBindingAudit(document,{locate:row=>located.push(row),apiRequest:async(_url,init)=>{if(init.method==='POST')posts.push(JSON.parse(init.body));return response;}});
 ui.sync(job,true);await ui.request();
 const select=all(ui.element).find(n=>n.tag==='select');assert.equal(select.value,'not_reviewed');
 all(ui.element).find(n=>n.textContent==='正在检查').onclick();assert.deepEqual(located,[]);
 assert.match(all(ui.element).find(n=>n.tag==='iframe').src,/\/view\/player.html/);
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
