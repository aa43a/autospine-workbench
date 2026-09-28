import test from 'node:test';
import assert from 'node:assert/strict';
import {createJointWorkflow} from '../modules/motion-joint-editor-workflow.js';
import {JOINT_SCHEMA,jointDraftKey} from '../modules/motion-joint-editor-state.js';
const parent={job_id:`motion-${'a'.repeat(32)}`,kind:'adapt',status:'succeeded',result:{artifact_sha256:'b'.repeat(64)}};
const metadata={parent_job_id:parent.job_id,artifact_sha256:parent.result.artifact_sha256,animation:'external-motion',duration:2,
  defaults:{schema:JOINT_SCHEMA,seed:0,fps:30,loop:false,face:{enabled:true},hair:{enabled:true},cloth:{enabled:true}},
  controls:[{group:'face',key:'enabled',label:'脸部',type:'boolean'}]};
const child=`motion-${'c'.repeat(32)}`,retry=`motion-${'d'.repeat(32)}`;
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function harness(request){
  const store=new Map(),state={view:null,selection:'alice',calls:[],inspected:[],timers:[]};
  const flow=createJointWorkflow({request:async(...args)=>{state.calls.push(args);return request(...args);},
    getSelection:()=>({project_id:state.selection}),notify:(model,status)=>{state.view={...status,changed:model.changed};},
    inspect:job=>state.inspected.push(job.job_id),storage:{getItem:key=>store.get(key),setItem:(key,value)=>store.set(key,value)},
    schedule:fn=>{state.timers.push(fn);return state.timers.length;},unschedule:()=>{}});
  return {flow,state,store};
}
test('late metadata from previous source never populates a new selection',async()=>{
  const pending=deferred(),{flow,state}=harness(()=>pending.promise);
  const load=flow.load(parent);state.selection='huiye';flow.reset();pending.resolve(metadata);await load;
  assert.equal(flow.state.meta,null);assert.equal(state.view.busy,false);
});
test('submit captures config, source reset ignores old successful task without inspection',async()=>{
  const submit=deferred(),{flow,state}=harness((url,body)=>body?submit.promise:metadata);
  await flow.load(parent);const build=flow.build();assert.equal(state.view.busy,true);
  state.selection='huiye';flow.reset();submit.resolve({job_id:child,status:'pending'});await build;
  assert.equal(flow.state.meta,null);assert.deepEqual(state.inspected,[]);assert.equal(state.view.job,null);
});
test('poll errors retain active job and allow cancellation rather than duplicate submission',async()=>{
  let polls=0;const {flow,state}=harness((url,body)=>{
    if(url.endsWith('joint-animation'))return body?{job_id:child,status:'pending'}:metadata;
    if(url.endsWith('/cancel'))return {};
    if(++polls===1)throw Error('offline');return {job_id:child,kind:'adapt',status:'cancelled'};
  });
  await flow.load(parent);await flow.build();await flush();
  assert.match(state.view.message,/暂时无法/);assert.equal(state.view.job.status,'pending');
  const calls=state.calls.length;await flow.build();assert.equal(state.calls.length,calls);
  await flow.cancel();await flush();assert.equal(state.view.job.status,'cancelled');
  assert.equal(state.calls.filter(([url])=>url.endsWith('/cancel')).length,1);
});
test('failure retry creates a distinct task and preserves the submitted snapshot',async()=>{
  const {flow,state,store}=harness((url,body)=>{
    if(url.endsWith('joint-animation'))return body?{job_id:child,status:'pending'}:metadata;
    if(url.endsWith('/retry'))return {job_id:retry,status:'pending'};
    return {job_id:url.split('/').at(-1),kind:'adapt',status:url.endsWith(child)?'failed':'succeeded',result:{artifact_sha256:'e'.repeat(64)}};
  });
  await flow.load(parent);await flow.build();await flush();flow.change('face','enabled',false);
  await flow.retry();await flush();assert.equal(state.view.job.job_id,retry);assert.equal(state.view.changed,true);
  assert.deepEqual(state.inspected,[retry]);const persisted=JSON.parse(store.get(`${jointDraftKey(metadata)}:task`));
  assert.equal(persisted.config.face.enabled,true);assert.equal(persisted.job_id,retry);
});
test('a slower poll cannot overwrite a newer successful poll',async()=>{
  const slow=deferred();let polls=0;const {flow,state}=harness((url,body)=>{
    if(url.endsWith('joint-animation'))return body?{job_id:child,status:'pending'}:metadata;
    return ++polls===1?slow.promise:{job_id:child,kind:'adapt',status:'succeeded',result:{artifact_sha256:'e'.repeat(64)}};
  });
  await flow.load(parent);await flow.build();await flow.refresh();
  slow.resolve({job_id:child,kind:'adapt',status:'running'});await flush();
  assert.equal(state.view.job.status,'succeeded');assert.deepEqual(state.inspected,[child]);
});
test('missing restored task retains parameters and permits rebuilding instead of polling forever',async()=>{
  const {flow,state,store}=harness(url=>{if(url.endsWith('joint-animation'))return metadata;throw Object.assign(Error('missing'),{status:404});});
  store.set(`${jointDraftKey(metadata)}:task`,JSON.stringify({job_id:child,config:{...metadata.defaults,face:{enabled:false}}}));
  await flow.load(parent);await flush();assert.equal(flow.state.config.face.enabled,false);assert.equal(state.view.job.status,'outdated');
  assert.equal(state.timers.length,0);assert.match(state.view.message,/重新构建/);
});
test('unsupported body keeps authoring readable but never submits a new build',async()=>{
  const {flow,state}=harness(()=>({...metadata,eligibility:{supported:false,message:'附件切换暂不支持'}}));
  await flow.load(parent);flow.change('face','enabled',false);await flow.build();
  assert.equal(state.calls.filter(([,body])=>body!==undefined).length,0);assert.match(state.view.message,/附件切换/);
});
test('related body metadata and build remain bound to the selected registration',async()=>{
  const registration='e'.repeat(64),candidate={...parent,joint_registration_sha256:registration};
  const {flow,state}=harness((url,body)=>url.endsWith('joint-animation')?(body?{job_id:child,status:'pending'}:{...metadata,registration_sha256:registration}):{job_id:child,kind:'adapt',status:'running'});
  await flow.load(candidate);await flow.build();await flush();
  assert.equal(state.calls[0][0],`/api/motions/${parent.job_id}/related-candidates/${registration}/joint-animation`);
  assert.equal(state.calls.find(([,body])=>body!==undefined)[1].registration_sha256,registration);
  const mismatch=harness(()=>({...metadata,registration_sha256:'f'.repeat(64)}));await mismatch.flow.load(candidate);
  assert.equal(mismatch.flow.state.meta,null);assert.match(mismatch.state.view.message,/不匹配/);
});
