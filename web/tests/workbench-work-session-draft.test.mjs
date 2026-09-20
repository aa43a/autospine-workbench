import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkSessions} from '../modules/workbench-work-sessions.js';
import {createSessionDrafts} from '../modules/workbench-work-session-draft.js';
const all=n=>[n,...n.children.flatMap(all)],flush=()=>new Promise(r=>setImmediate(r));
const memory=()=>{const map=new Map();return {getItem:k=>map.get(k),setItem:(k,v)=>map.set(k,v),removeItem:k=>map.delete(k)};};
function setup(storage,clock,posts,sessions=[]){
 const listeners={},host={sessionStorage:storage,addEventListener:(k,v)=>listeners[k]=v,removeEventListener:k=>delete listeners[k],setInterval:f=>(listeners.tick=f,1),clearInterval:()=>delete listeners.tick};
 const document={defaultView:host,createElement(tag){return {tag,children:[],append(...n){this.children.push(...n)},replaceChildren(...n){this.children=n},setAttribute(){}}}};
 const ui=createWorkSessions(document,{clock,context:()=>({projectId:'p'}),apiRequest:async(url,init)=>{if(init.method==='POST')posts.push(JSON.parse(init.body));return {project_id:'p',authority:'none',source_sha256:'source',head_sha256:null,sessions,metrics:{recorded_minutes:null}};}});
 return {ui,listeners,button:text=>all(ui.element).find(n=>n.textContent===text)};
}
test('reload restores paused exact segment, excluding offline elapsed time',async()=>{
 const storage=memory(),posts=[];let now=100000;
 const first=setup(storage,()=>now,posts);first.ui.sync();await flush();first.button('开始本阶段计时').onclick();now+=6000;first.listeners.pagehide();first.ui.dispose();
 now+=600000;const second=setup(storage,()=>now,posts);second.ui.sync();await flush();
 assert.equal(posts.length,0);assert.ok(second.button('项目人工工作计时 · 有未保存计时'));
 second.button('暂停并保存').onclick();await flush();assert.equal(posts[0].payload.seconds,6);assert.equal(posts[0].expected_source_sha256,'source');
 assert.equal(createSessionDrafts(storage).read('p'),null);second.ui.dispose();
});
test('crash recovery uses last checkpoint; matching server receipt clears retry',async()=>{
 const storage=memory(),posts=[];let now=100000;
 const first=setup(storage,()=>now,posts);first.ui.sync();await flush();first.button('开始本阶段计时').onclick();now+=5000;first.listeners.tick();
 const pending=createSessionDrafts(storage).read('p');assert.equal(pending.seconds,5);
 now+=100000;const restored=setup(storage,()=>now,posts,[{...pending,source_sha256:pending.source}]);restored.ui.sync();await flush();
 assert.equal(createSessionDrafts(storage).read('p'),null);assert.equal(posts.length,0);restored.ui.dispose();
});
test('invalid drafts and cross-project copies do not become work records',()=>{
 const storage=memory(),store=createSessionDrafts(storage);
 const draft={source:'s',session_id:'a'.repeat(32),stage:'joints',started_at:new Date(0).toISOString(),ended_at:new Date(5000).toISOString(),seconds:5,method:'operator_stopwatch_segment_v1'};
 assert.equal(store.write('p',draft),true);assert.equal(store.read('q'),null);
 assert.equal(store.write('p',{...draft,seconds:100}),false);assert.equal(store.write('p',{...draft,stage:'fake'}),false);
 storage.setItem('autospine:work-session-draft:v1:q',storage.getItem('autospine:work-session-draft:v1:p'));assert.equal(store.read('q'),null);
 storage.setItem('autospine:work-session-draft:v1:p','invalid');assert.equal(store.read('p'),null);
});
test('storage denial warns without losing the in-memory segment',async()=>{
 const storage={getItem(){throw Error('denied')},setItem(){throw Error('denied')},removeItem(){throw Error('denied')}};
 let now=100000;const posts=[],view=setup(storage,()=>now,posts);view.ui.sync();await flush();view.button('开始本阶段计时').onclick();
 assert.ok(all(view.ui.element).some(n=>n.textContent?.includes('浏览器未能暂存')));
 now+=3000;view.button('暂停并保存').onclick();await flush();assert.equal(posts[0].payload.seconds,3);view.ui.dispose();
});
