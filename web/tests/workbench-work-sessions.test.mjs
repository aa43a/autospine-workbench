import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkSessions} from '../modules/workbench-work-sessions.js';
const document={createElement(tag){return {tag,children:[],append(...nodes){this.children.push(...nodes);},replaceChildren(...nodes){this.children=nodes;},setAttribute(){}};}};
const all=n=>[n,...n.children.flatMap(all)];
const flush=()=>new Promise(r=>setImmediate(r));
test('project switch pauses draft, returning restores it, and saved source remains exact',async()=>{
 let projectId='a',now=100000,posts=[];
 const ui=createWorkSessions(document,{clock:()=>now,context:()=>({projectId}),apiRequest:async(url,init)=>{
  if(init.method==='POST')posts.push(JSON.parse(init.body));
  return {project_id:projectId,authority:'none',source_sha256:projectId,head_sha256:null,sessions:[],metrics:{recorded_minutes:null}};
 }});
 const button=text=>all(ui.element).find(n=>n.textContent===text);
 ui.sync();await flush();button('开始本阶段计时').onclick();now+=60000;
 projectId='b';ui.sync();await flush();projectId='a';ui.sync();await flush();button('暂停并保存').onclick();await flush();
 assert.equal(posts.length,1);assert.equal(posts[0].payload.seconds,60);assert.equal(posts[0].expected_source_sha256,'a');assert.equal(posts[0].payload.source,undefined);ui.dispose();
});
test('failed save retains segment and does not silently advance the clock',async()=>{
 let now=100000;
 const ui=createWorkSessions(document,{clock:()=>now,context:()=>({projectId:'p'}),apiRequest:async(url,init)=>{if(init.method==='POST')throw Error('offline');return {project_id:'p',authority:'none',source_sha256:'s',head_sha256:null,sessions:[],metrics:{recorded_minutes:null}};}});
 ui.sync();await flush();all(ui.element).find(n=>n.textContent==='开始本阶段计时').onclick();now+=5000;all(ui.element).find(n=>n.textContent==='暂停并保存').onclick();await flush();
 assert.ok(all(ui.element).some(n=>n.textContent==='项目人工工作计时 · 有未保存计时'));ui.dispose();
});
