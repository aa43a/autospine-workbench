import {test} from 'node:test';
import assert from 'node:assert/strict';
import {buildProgressText,createEditorBuild} from '../modules/motion-editor-build.js';

test('reports observed work and Unix update time, never a fabricated overall percentage',()=>{
  const text=buildProgressText({status:'running',step:'retarget',elapsed_seconds:125,timeout_seconds:3600,
    progress:{updated_at:1000,stage:'solve_attachment',slot:'arm',slot_index:2,total_slots:8,iteration:1,max_rounds:4}},1012000);
  assert.match(text,/2 分 5 秒/);assert.match(text,/图层 arm/);assert.match(text,/图层 3 \/ 8/);
  assert.match(text,/修正轮次 2 \/ 4/);assert.match(text,/12 秒 前/);assert.doesNotMatch(text,/%/);
  assert.doesNotMatch(buildProgressText({status:'running',step:'retarget'}),/NaN|undefined/);
  assert.equal(buildProgressText({status:'succeeded',step:'complete',progress:{step:'retarget',stage:'solve_attachment'}}),'处理结束');
  const frame=buildProgressText({status:'running',step:'retarget',progress:{frame_index:32,sample_count:100,completed:32,total:100}});
  assert.match(frame,/采样 33 \/ 100/);assert.doesNotMatch(frame,/本阶段/);
});

test('temporary polling failures retain active lock and retry until terminal status',async()=>{
  const saved={document:globalThis.document,window:globalThis.window,location:globalThis.location,
    fetch:globalThis.fetch,setTimeout:globalThis.setTimeout,clearTimeout:globalThis.clearTimeout};
  const elements=Object.fromEntries(['build','build-status','build-result','cancel-build','refresh-build'].map(id=>[id,{disabled:false,replaceChildren(){},append(){}}]));
  const timers=new Map();let next=0,requests=0;
  try{
    globalThis.document={getElementById:id=>elements[id],createElement:()=>({})};
    globalThis.window={addEventListener(){}};globalThis.location={hash:'#motion-'+'a'.repeat(32)};
    globalThis.setTimeout=fn=>{timers.set(++next,fn);return next;};globalThis.clearTimeout=id=>timers.delete(id);
    globalThis.fetch=async()=>{requests++;if(requests===1)throw Error('network unavailable');return {ok:true,json:async()=>({kind:'adapt',job_id:'motion-'+'a'.repeat(32),status:'failed',step:'retarget',reason_code:'motion_target_stalled'})};};
    createEditorBuild({snapshot(){throw Error('must not submit');}});
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(elements.build.disabled,true);assert.match(elements['build-status'].textContent,/自动重试/);assert.equal(timers.size,1);
    await elements.build.onclick();assert.equal(requests,1);
    await [...timers.values()][0]();
    assert.equal(elements.build.disabled,false);assert.match(elements['build-status'].textContent,/长时间没有更新进度/);assert.equal(timers.size,0);
  }finally{Object.assign(globalThis,saved);}
});
