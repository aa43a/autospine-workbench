import test from 'node:test';
import assert from 'node:assert/strict';
import { createWorkbenchCharacter } from '../modules/workbench-character.js';

const flush = () => new Promise(resolve => setImmediate(resolve));
function fixture(api) {
  const document = {createElement(tag) {return {tag, children:[],events:{},attrs:{},
    append(...nodes){this.children.push(...nodes);},replaceChildren(...nodes){this.children=nodes;},
    setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];},
    addEventListener(k,v){this.events[k]=v;}};}};
  const context={projectId:'one',resolvedSha:'a'.repeat(64)}, timers=new Map();
  const view=createWorkbenchCharacter(document,{context:()=>context,apiRequest:api},{
    setTimeout(fn){const key=Symbol();timers.set(key,fn);return key;},clearTimeout(key){timers.delete(key);}});
  const [,,actions,status,download,details]=view.element.children;
  return {view,context,timers,status,download,details,build:actions.children[0]};
}
const job=(status='needs_review')=>({schema:'autospine.character-web-job/v1',project_id:'one',authority:'none',
  job_id:'job-'+ 'b'.repeat(32),status,stage:status==='running'?'compose':'review',layers:[]});
const overview=value=>({project_id:'one',authority:'none',can_build:true,job:value});

test('restored terminal candidate stops polling and dirty edits suppress download',async()=>{
  const f=fixture(async()=>overview(job()));f.view.sync();await flush();
  assert.equal(f.download.hidden,false);assert.equal(f.timers.size,0);
  assert.match(f.download.attrs.href,/\/one\/automation\/character\/jobs\/job-/);
  f.context.dirty=true;f.view.sync();assert.equal(f.download.hidden,true);
  assert.equal(f.build.disabled,true);assert.equal(f.download.attrs.href,undefined);
  f.view.dispose();
});

test('poll retains meaningful stage then stops on terminal response',async()=>{
  let calls=0;const f=fixture(async()=>++calls===1?overview(job('running')):job());
  f.view.sync();await flush();assert.match(f.status.textContent,/合并袖装/);
  assert.equal(f.timers.size,1);const [key,run]=[...f.timers][0];f.timers.delete(key);run();await flush();
  assert.equal(calls,2);assert.equal(f.timers.size,0);assert.equal(f.download.hidden,false);
  f.view.dispose();
});

test('late response from previous project cannot restore its download',async()=>{
  let release;const f=fixture(()=>new Promise(resolve=>{release=resolve;}));
  f.view.sync();f.context.projectId=null;f.view.sync();release(overview(job()));await flush();
  assert.equal(f.download.hidden,true);assert.equal(f.timers.size,0);
  assert.equal(f.details.hidden,true);assert.equal(f.build.disabled,true);f.view.dispose();
});

test('verified report links track current job and hide on unsaved edits',async()=>{
  const current=job();current.runtime={files:{'index.html':'a','setup/index.html':'b'}};
  const f=fixture(async()=>overview(current));f.view.sync();await flush();
  const [runtime,setup]=f.view.element.children.slice(-2);
  assert.equal(runtime.hidden,false);assert.match(setup.attrs.href,/\/view\/setup\/index.html$/);
  f.context.dirty=true;f.view.sync();assert.equal(runtime.hidden,true);assert.equal(setup.attrs.href,undefined);
  f.view.dispose();
});
