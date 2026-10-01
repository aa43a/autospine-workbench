import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {windVectors,windParameters,springSolve,angularWind} from '../modules/motion-wind-solver.js';
import {jointWindPreview,windOffsets,applyWindOffsets,validateWindTemplate,windPreviewGain} from '../modules/motion-wind-preview.js';
import {createJointState,jointDraft,restoreJointDraft} from '../modules/motion-joint-editor-state.js';
import {readWindTemplate} from '../modules/motion-editor-result.js';

const cwd=fileURLToPath(new URL('../../',import.meta.url));
const python=code=>{const r=spawnSync('python',['-c',code],{cwd,encoding:'utf8',maxBuffer:10*1024*1024,env:{...process.env,PYTHONPATH:'src;tests'}});
  assert.equal(r.status,0,r.stderr);return JSON.parse(r.stdout);};
const fixture=python('import json; from test_joint_wind import preview_fixture; print(json.dumps(preview_fixture()))');

test('published wind resource is source-bound and a failed fetch is explicit',async()=>{
  const template=structuredClone(fixture.template),report={duration:2,skeleton_sha256:'s',parent_skeleton_sha256:'p',config_sha256:'c'};
  Object.assign(template,report);const raw=JSON.stringify(template);
  report.secondary={wind_preview:{file:'wind-preview.json',sha256:createHash('sha256').update(raw).digest('hex')}};
  assert.equal(JSON.stringify(await readWindTemplate('job',report,fixture.document,async url=>{
    assert.equal(url,'/api/motions/job/view/wind-preview.json');return new Response(raw);
  })),raw);
  await assert.rejects(readWindTemplate('job',report,fixture.document,async()=>new Response(null,{status:400})),/400/);
  await assert.rejects(readWindTemplate('job',report,fixture.document,async()=>new Response('{}')),/版本/);
  assert.equal(await readWindTemplate('old',{},fixture.document),null);
});

test('browser and export spring trajectories agree for hair cascade and cloth wind, including baking and guard gain',()=>{
  const {template,report,config,document}=fixture;
  const preview=jointWindPreview(template,{...report,config,inventory:{}},config);
  const withReview={...report,config,inventory:{},secondary:{geometry_guard:[{slot:template.regions[0].slot,
    collision:{policy:'diagnostic'},history:[{collision_failed_samples:2}]}]}};
  assert.equal(jointWindPreview(template,withReview,config).regions[0].built_projected_overlap,true);
  assert.equal(preview.regions[0].built_projected_overlap,false);
  for(const row of report.regions)for(const helper of row.helpers){
    const keys=document.animations.idle.bones[helper].rotate,track=preview.tracks.get(helper);
    assert.deepEqual(track.times,keys.map(k=>k.time));
    assert.ok(Math.max(...keys.map((k,i)=>Math.abs(k.value-track.values[i])))<1e-10,helper);
  }
  const times=[.31,1.8,.91],first=times.map(t=>[...windOffsets(preview,t)]);
  for(const t of [...times].reverse())windOffsets(preview,t);
  assert.deepEqual(times.map(t=>[...windOffsets(preview,t)]),first);
  const sorted=JSON.parse(JSON.stringify(config,(key,value)=>value&&typeof value==='object'&&!Array.isArray(value)?Object.fromEntries(Object.keys(value).sort().map(k=>[k,value[k]])):value));
  assert.equal(jointWindPreview(template,{...report,config:sorted,inventory:{}},config).changed,false,
    'canonical server JSON key order must not mark an unchanged draft as edited');
});

test('direction, gust keys and a switched-off field match the Python solver through all ticks',()=>{
  const data=python("import json; from autospine_workbench.targets.character43.joint_wind import defaults,vectors,angular_forces; from autospine_workbench.targets.character43.joint_spring import grid,solve; t=grid(2.); p=[(0.,0.,-90.) for _ in t]; c=dict(defaults(),enabled=True,seed=77,keys=[dict(time=0.,strength=50.,direction=350.),dict(time=1.,strength=20.,direction=10.),dict(time=2.,strength=0.,direction=180.)]); w,r=vectors(c,t); a=angular_forces(w,p); v,e=solve(t,p,external_forces=a,max_angle=10.); print(json.dumps(dict(config=c,times=t,poses=p,vectors=w,values=v)))");
  const {values}=windVectors(data.config,data.times);assert.ok(Math.max(...values.map((p,i)=>Math.hypot(p[0]-data.vectors[i][0],p[1]-data.vectors[i][1])))<1e-12);
  const result=springSolve(data.times,data.poses,{external:angularWind(values,data.poses),max_angle:10});
  assert.ok(Math.max(...result.map((v,i)=>Math.abs(v-data.values[i])))<1e-11);
  const off=windVectors({...data.config,enabled:false},data.times).values;
  assert.equal(Math.max(...springSolve(data.times,data.poses,{external:angularWind(off,data.poses)}).map(Math.abs)),0);
  assert.deepEqual(windParameters({...data.config,keys:data.config.keys.slice(0,2)},.5),[35,360]);
});

test('no-wind comparison preserves carrier inertia, and application changes only generated helpers',()=>{
  const {template,report,config}=fixture,full={...report,config,inventory:{}};
  const original=JSON.stringify(fixture),withWind=jointWindPreview(template,full,config),without=jointWindPreview(template,full,config,{noWind:true});
  const offsets=windOffsets(withWind,1),off=windOffsets(without,1);
  assert.ok([...off.values()].some(v=>Math.abs(v)>1e-4));
  assert.ok([...offsets].some(([n,v])=>Math.abs(v-off.get(n))>.01));
  const skeleton={bones:[{data:{name:'head'},pose:{rotation:15}},...[...offsets].map(([name])=>({data:{name},pose:{rotation:99}}))]};
  applyWindOffsets(skeleton,offsets,new Map());assert.equal(skeleton.bones[0].pose.rotation,15);
  for(const bone of skeleton.bones.slice(1))assert.equal(bone.pose.rotation,offsets.get(bone.data.name));
  assert.equal(JSON.stringify(fixture),original);assert.equal(without.noWind,true);
  assert.ok(without.pending.some(p=>p.includes('Runtime')));
});

test('wind keyframes are source-bound, undoable, bounded and migrate old drafts with wind disabled',()=>{
  const defs=python('import json; from autospine_workbench.targets.character43.joint_animation_config import defaults,controls; print(json.dumps(dict(defaults=defaults(),controls=controls())))');
  const parent={job_id:'motion-'+'a'.repeat(32),kind:'adapt',status:'succeeded',result:{artifact_sha256:'b'.repeat(64)}};
  const meta={...defs,parent_job_id:parent.job_id,artifact_sha256:parent.result.artifact_sha256,duration:2,inventory:{hair:[{slot:'back',state:'available'}]}};
  const state=createJointState();state.load(meta,parent);state.enableWind();assert.equal(state.config.wind.enabled,true);assert.equal(state.config.hair.enabled,true);assert.equal(state.config.cloth.enabled,false);
  state.key('wind',0,{strength:30,direction:350});state.key('wind',2,{strength:60,direction:10});
  assert.deepEqual(restoreJointDraft(jointDraft(meta,state.config),meta),state.config);
  state.undo();assert.equal(state.config.wind.keys.length,1);state.redo();assert.equal(state.config.wind.keys.length,2);
  state.change('wind','seed',3);assert.throws(()=>state.change('wind','seed',.5),/格式/);
  assert.throws(()=>state.key('wind',2.1,{strength:20,direction:0}),/时间/);
  assert.throws(()=>state.key('wind',1,{strength:120,direction:0}),/范围/);
  state.deleteKey('wind',2);state.clearKeys('wind');assert.equal(state.config.wind.keys.length,0);
  const old=jointDraft(meta,state.config);delete old.config.wind;for(const group of ['hair','cloth','objects'])delete old.config[group].wind_response;
  assert.equal(restoreJointDraft(old,meta).wind.enabled,false);
});

test('tampered source identity or helper ownership cannot turn wind preview into body edits',()=>{
  const f=structuredClone(fixture),report={duration:2,skeleton_sha256:'s',parent_skeleton_sha256:'p',config_sha256:'c'};
  Object.assign(f.template,report);assert.equal(validateWindTemplate(f.template,report,f.document),f.template);
  assert.throws(()=>validateWindTemplate({...f.template,skeleton_sha256:'other'},report,f.document),/来源/);
  f.template.regions[0].helpers=['head'];assert.throws(()=>validateWindTemplate(f.template,report,f.document),/骨骼/);
});

test('keyed strength and direction edits update the evaluated time immediately without rewriting other keys',()=>{
  const defs=python('import json; from autospine_workbench.targets.character43.joint_animation_config import defaults,controls; print(json.dumps(dict(defaults=defaults(),controls=controls())))');
  const parent={job_id:'motion-'+'a'.repeat(32),kind:'adapt',status:'succeeded',result:{artifact_sha256:'b'.repeat(64)}};
  const meta={...defs,parent_job_id:parent.job_id,artifact_sha256:parent.result.artifact_sha256,duration:2,inventory:{}};
  const state=createJointState();state.load(meta,parent);
  state.key('wind',0,{strength:45,direction:345});state.key('wind',2,{strength:20,direction:15});
  const original=structuredClone(state.config.wind.keys);
  state.windParameter('strength',79,1);
  assert.deepEqual(windParameters(state.config.wind,1),[79,0]);
  assert.deepEqual([state.config.wind.keys[0],state.config.wind.keys[2]],original);
  state.undo();assert.deepEqual(state.config.wind.keys,original);state.redo();
  state.windParameter('direction',180,1);assert.deepEqual(windParameters(state.config.wind,1),[79,180]);
  state.clearKeys('wind',1);assert.deepEqual(windParameters(state.config.wind,1),[79,180]);assert.equal(state.config.wind.keys.length,0);
  state.undo();assert.equal(state.config.wind.keys.length,3);
  assert.throws(()=>state.windParameter('strength',80,2.1),/时间/);
});

test('equilibrium wind has a visible strength range and matches the export solver',()=>{
  const data=python("import json; from autospine_workbench.targets.character43.joint_wind import defaults,vectors,angular_forces; from autospine_workbench.targets.character43.joint_spring import grid,solve; t=grid(4.); p=[(0.,0.,-90.) for _ in t]; c=dict(defaults(),enabled=True,strength=75.,gust=.3,response_profile='bounded-equilibrium-v2'); w,r=vectors(c,t); f=angular_forces(w,p,profile=c['response_profile'],stiffness=36.,max_angle=6.); v,e=solve(t,p,max_angle=6.,external_forces=f); print(json.dumps(dict(config=c,times=t,poses=p,values=v)))");
  const result=springSolve(data.times,data.poses,{max_angle:6,external:angularWind(windVectors(data.config,data.times).values,data.poses,{profile:data.config.response_profile,max_angle:6})});
  assert.ok(Math.max(...result.map((v,i)=>Math.abs(v-data.values[i])))<1e-11);
  const peaks=[25,50,75,100].map(strength=>springSolve(data.times,data.poses,{max_angle:6,
    external:angularWind(windVectors({...data.config,strength,gust:0},data.times).values,data.poses,{profile:data.config.response_profile,max_angle:6})}).at(-1));
  assert.ok(peaks.every((v,i)=>!i||v>peaks[i-1]+.2));
  const record={slot:'hair',post_solve_gain:.125},config={wind:{response_profile:'bounded-equilibrium-v2'}};
  const report={config:{wind:{}},secondary:{geometry_guard:[{slot:'hair',history:[{gain:1,min_area_ratio:.98,max_area_ratio:1.02,max_edge_stretch:1.05}]}]}};
  assert.equal(windPreviewGain(record,report,config),1);
  report.secondary.geometry_guard[0].history[0].min_area_ratio=-1;assert.equal(windPreviewGain(record,report,config),.125);
});
