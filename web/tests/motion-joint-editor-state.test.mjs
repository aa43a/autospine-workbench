import test from 'node:test';
import assert from 'node:assert/strict';
import {createJointState,JOINT_SCHEMA,jointDraft,restoreJointDraft,jointValue,setJointValue,validateJointConfig} from '../modules/motion-joint-editor-state.js';

export const parent={job_id:`motion-${'a'.repeat(32)}`,kind:'adapt',status:'succeeded',result:{artifact_sha256:'b'.repeat(64)}};
export const metadata={parent_job_id:parent.job_id,artifact_sha256:parent.result.artifact_sha256,animation:'external-motion',duration:2,
  inventory:{features:[{label:'眨眼',available:true}]},
  defaults:{schema:JOINT_SCHEMA,seed:0,fps:30,loop:false,face:{enabled:true,blink:{enabled:true,keys:[],period:2},
    gaze:{enabled:true,x:0,y:0,keys:[]},anchors:{eyes:[12,34]}},hair:{enabled:true,strength:0.4},cloth:{enabled:true,strength:0.5}},
  controls:[{group:'face',key:'enabled',label:'脸部',type:'boolean'},{group:'face',key:'gaze.x',label:'视线',type:'number',min:-1,max:1,animatable:true,channel:'gaze'},
    {group:'hair',key:'strength',label:'发束幅度',type:'number',min:0,max:2}]};

test('nested face edits retain keys and anchors, undo does not mutate source defaults',()=>{
  const state=createJointState();state.load(metadata,parent);state.change('face','gaze.x',0.6);
  state.key('gaze',0.5,{x:0.6,y:-0.2});assert.equal(state.config.face.gaze.keys[0].y,-0.2);
  state.change('hair','strength',0.9);assert.deepEqual(state.config.face.anchors,{eyes:[12,34]});
  state.undo();assert.equal(state.config.hair.strength,0.4);assert.equal(state.config.face.gaze.keys.length,1);
  state.undo();assert.equal(state.config.face.gaze.keys.length,0);state.redo();assert.equal(state.config.face.gaze.keys.length,1);
  assert.equal(metadata.defaults.face.gaze.x,0);assert.equal(metadata.defaults.face.gaze.keys.length,0);
});
test('draft belongs to exact immutable parent and result becomes stale after editing',()=>{
  const state=createJointState();state.load(metadata,parent);state.submit();state.change('face','gaze.x',1);
  assert.equal(state.changed,true);state.undo();assert.equal(state.changed,false);
  const draft=jointDraft(metadata,state.config);assert.deepEqual(restoreJointDraft(draft,metadata),state.config);
  assert.throws(()=>restoreJointDraft({...draft,artifact_sha256:'c'.repeat(64)},metadata),/不同/);
  state.reset();assert.equal(state.meta,null);assert.equal(state.canUndo,false);
});
test('key insertion replaces same time, deleting and clearing restore automatic channels',()=>{
  const state=createJointState();state.load(metadata,parent);state.key('blink',0.75,{value:0.5});state.key('blink',0.75,{value:1});
  assert.deepEqual(state.config.face.blink.keys,[{time:0.75,value:1}]);
  state.key('blink',0.1,{value:0});assert.equal(state.config.face.blink.keys[0].time,0.1);
  state.deleteKey('blink',0.75);assert.equal(state.config.face.blink.keys.length,1);
  state.clearKeys('blink');assert.deepEqual(state.config.face.blink.keys,[]);
});
test('invalid key ranges, duplicate times, unsafe paths and stale metadata are rejected',()=>{
  const state=createJointState();assert.throws(()=>state.load({...metadata,artifact_sha256:'c'.repeat(64)},parent),/版本/);
  state.load(metadata,parent);assert.throws(()=>state.key('blink',2.1,{value:0.5}),/时间/);
  assert.throws(()=>state.key('blink',1,{value:2}),/范围/);
  const config=structuredClone(state.config);config.face.gaze.keys=[{time:1,x:0,y:0},{time:1,x:0,y:1}];
  assert.throws(()=>validateJointConfig(config,metadata),/重复/);
  assert.throws(()=>jointValue({},'__proto__.x'),/无效/);assert.throws(()=>setJointValue({},'constructor.foo',1),/无效/);
});
test('anchor overrides are optional, reversible, bounded and restricted to supported parts',()=>{
  const state=createJointState(),meta={...metadata,inventory:{face:{parts:[{slot:'eyes',available:true,anchor:[12,34]}]}}};
  state.load(meta,parent);state.anchor('eyes',[16,30]);assert.deepEqual(state.config.face.anchors.eyes,[16,30]);
  state.anchor('eyes',null);assert.equal(state.config.face.anchors.eyes,undefined);state.undo();assert.deepEqual(state.config.face.anchors.eyes,[16,30]);
  assert.throws(()=>state.anchor('unknown',[0,0]),/可用/);assert.throws(()=>state.anchor('eyes',[9000,0]),/范围/);
});
test('rational final frame key can be recorded and deleted without exceeding exact duration',()=>{
  const state=createJointState();state.load({...metadata,duration:29/30},parent);
  state.key('blink',29/30,{value:1});assert.equal(state.config.face.blink.keys[0].time,29/30);
  state.deleteKey('blink',29/30);assert.equal(state.config.face.blink.keys.length,0);
});
test('secondary target selection only selects eligible slots and keeps all-target shorthand explicit',()=>{
  const state=createJointState();state.load({...metadata,inventory:{hair:[{slot:'back',state:'available'},{slot:'front',state:'available'},{slot:'old',state:'unsupported'}]}},parent);
  state.targets('hair',['back']);assert.deepEqual(state.config.hair.slots,['back']);
  state.targets('hair',['front','back']);assert.deepEqual(state.config.hair.slots,[]);
  assert.throws(()=>state.targets('hair',[]),/关闭/);assert.throws(()=>state.targets('hair',['old']),/不一致/);
});
test('local response overrides stay sparse, reversible and reject incompatible target parameters',()=>{
  const state=createJointState(),meta={...metadata,inventory:{hair:[{slot:'back',state:'available'}],cloth:[{slot:'skirt',state:'available'}]}};
  state.load(meta,parent);state.local('hair','back',{strength:.7,root_fraction:.5});
  assert.deepEqual(state.config.hair.overrides.back,{strength:.7,root_fraction:.5});
  state.change('hair','strength',1);assert.equal(state.config.hair.overrides.back.stiffness,undefined);
  state.local('hair','back',null);assert.deepEqual(state.config.hair.overrides,{});state.undo();assert.equal(state.config.hair.overrides.back.strength,.7);
  assert.throws(()=>state.local('cloth','skirt',{root_fraction:.5}),/范围/);
  assert.throws(()=>state.local('hair','back',{damping:0}),/范围/);
  assert.throws(()=>state.local('hair','wrong',{strength:.5}),/不一致/);
  assert.deepEqual(restoreJointDraft(jointDraft(meta,state.config),meta),state.config);
});
test('mouth replacement is preserved in drafts and reversible without accepting a file path',()=>{
  const state=createJointState(),meta=structuredClone(metadata);meta.defaults.face.mouth={template_image:null};state.load(meta,parent);
  const image={png_base64:'aW1hZ2U=',sha256:'c'.repeat(64)};state.mouthAsset(image);
  assert.deepEqual(restoreJointDraft(jointDraft(meta,state.config),meta).face.mouth.template_image,image);
  state.mouthAsset(null);state.undo();assert.deepEqual(state.config.face.mouth.template_image,image);
  assert.throws(()=>state.mouthAsset({...image,path:'C:/private.png'}),/格式/);
});
