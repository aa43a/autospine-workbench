import assert from 'node:assert/strict';
import {test} from 'node:test';
import {appendSupportExport} from '../modules/motion-support-export.js';
import {fixture} from './motion-support-fixture.mjs';
// Component/request tests only. No browser, DOM engine, layout or GPU is used.
class Node{
  constructor(tag){this.tag=tag;this.children=[];this.textContent='';}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=items;}
  setAttribute(){}
}
const all=n=>[n,...n.children.filter(c=>c instanceof Node).flatMap(all)];
function harness(){
  const f=fixture(),root=new Node('main'),events={},created=[],revoked=[];
  globalThis.document={createElement:tag=>new Node(tag)};
  globalThis.window={addEventListener:(name,fn)=>events[name]=fn};globalThis.location={origin:'http://127.0.0.1:8918'};
  globalThis.fetch=async path=>({ok:true,json:()=>f.get(path)});
  const originalCreate=URL.createObjectURL,originalRevoke=URL.revokeObjectURL;
  URL.createObjectURL=blob=>{created.push(blob);return 'blob:local/'+created.length;};
  URL.revokeObjectURL=url=>revoked.push(url);
  appendSupportExport(root,f.pack);
  return {...f,root,events,created,revoked,
    start:all(root).find(n=>n.textContent==='核对并生成支持范围报告'),stop:all(root).find(n=>n.textContent==='停止生成'),
    restore:()=>{URL.createObjectURL=originalCreate;URL.revokeObjectURL=originalRevoke;}};
}
test('exports both full report formats without mutating APIs, then invalidates on review change',async()=>{
  const h=harness();try{
    await h.start.onclick();assert.equal(h.created.length,2);assert.equal(all(h.root).filter(n=>n.tag==='a').length,2);
    const snapshot=JSON.parse(await h.created[1].text());assert.equal(snapshot.expected,2);
    assert.equal(snapshot.rows[0].review.current_applies,true);assert.equal(h.start.disabled,false);
    h.events['motion-stage-review-saved']({detail:{jobId:h.targetId}});
    assert.equal(all(h.root).filter(n=>n.tag==='a').length,0);assert.equal(h.revoked.length,2);
    assert.ok(all(h.root).some(n=>n.textContent.includes('阶段结论已更新')));
    assert.ok(h.calls.every(p=>p.startsWith('/api/motions/')));
  }finally{h.restore();}
});
for(const event of ['stop','motion-related-review-saved','pagehide'])test(`late result cannot recreate a download after ${event}`,async()=>{
  const h=harness();try{
    const originalFetch=globalThis.fetch;let finish,enter;
    const entered=new Promise(resolve=>enter=resolve);
    globalThis.fetch=async path=>{if(path.endsWith('/stage-review')){enter();await new Promise(resolve=>finish=resolve);}return originalFetch(path);};
    const run=h.start.onclick();await entered;
    if(event==='stop')h.stop.onclick();else h.events[event]({detail:{jobId:h.targetId}});
    finish();await run;
    assert.equal(h.created.length,0);assert.equal(all(h.root).filter(n=>n.tag==='a').length,0);
  }finally{h.restore();}
});
