import test from 'node:test';
import assert from 'node:assert/strict';
import {jointAmplitudePreview,applyJointAmplitude,jointPreviewText} from '../modules/motion-joint-preview.js';

const settings=()=>({enabled:true,strength:1,stiffness:25,damping:.9,max_angle:2,slots:[],overrides:{}});
function fixture(){
  const config={face:{enabled:true},hair:settings(),cloth:settings(),objects:settings(),loop:false,seed:0,fps:60};
  const rows=['hair','cloth','objects'].map(kind=>({region_kind:kind,slot:kind,helpers:[`m5-${kind==='cloth'?'response':kind==='objects'?'object':kind}-${kind}`],
    requested_config:{strength:1},post_solve_gain:.25}));
  const document={bones:[{name:'body',rotation:20},...rows.map(row=>({name:row.helpers[0],rotation:30}))],
    animations:{move:{bones:Object.fromEntries(rows.map(row=>[row.helpers[0],{rotate:[{time:0,value:0},{time:1,value:2}]}]))}}};
  const report={config:structuredClone(config),animation:'move',secondary:{regions:rows},inventory:Object.fromEntries(rows.map(row=>[row.region_kind,[{slot:row.slot,state:'available'}]]))};
  return {config,document,report};
}

test('scales only generated secondary helpers, with per-slot overrides and no source mutation',()=>{
  const {config,document,report}=fixture(),original=JSON.stringify({document,report});
  config.hair.strength=.4;config.cloth.enabled=false;config.objects.overrides.objects={strength:1.6};
  const preview=jointAmplitudePreview(document,report,config);
  assert.equal(preview.gains.get('m5-hair-hair'),.4);assert.equal(preview.gains.get('m5-response-cloth'),0);
  assert.equal(preview.gains.get('m5-object-objects'),1.6);assert.equal(preview.gains.has('body'),false);
  assert.equal(preview.changed,true);assert.deepEqual(preview.pending,[]);assert.equal(JSON.stringify({document,report}),original);
});

test('local strength override remains independent of the group strength slider',()=>{
  const {config,document,report}=fixture();report.config.hair.overrides.hair={strength:.6};
  report.secondary.regions[0].requested_config.strength=.6;config.hair.overrides.hair={strength:.6};config.hair.strength=.2;
  assert.equal(jointAmplitudePreview(document,report,config).gains.get('m5-hair-hair'),1);
});

test('zero-strength and guard-suppressed tracks cannot fabricate missing motion',()=>{
  const {config,document,report}=fixture();report.secondary.regions[0].requested_config.strength=0;
  report.secondary.regions[1].post_solve_gain=0;config.cloth.strength=1.5;
  const preview=jointAmplitudePreview(document,report,config);
  assert.equal(preview.gains.get('m5-hair-hair'),1);assert.equal(preview.gains.get('m5-response-cloth'),1);
  assert.equal(preview.pending.filter(row=>row.includes('没有可缩放')).length,2);
});

test('new region, non-amplitude params and face changes are explicitly deferred to rebuild',()=>{
  const {config,document,report}=fixture();report.inventory.hair.push({slot:'other',state:'available'});
  config.hair.stiffness=40;config.objects.anchor_x=.4;config.face.enabled=false;config.cloth.max_angle=3;
  const preview=jointAmplitudePreview(document,report,config);
  for(const fragment of ['other','刚度','挂点','表情','角度上限'])assert.ok(preview.pending.some(p=>p.includes(fragment)));
  assert.match(jointPreviewText(preview),/尚需构建/);
});

test('a motionless source response is not represented as a successful motion change',()=>{
  const {config,document,report}=fixture();report.secondary.regions[0].motion_status='static_driver_no_inertia';config.hair.strength=2;
  const preview=jointAmplitudePreview(document,report,config);assert.equal(preview.gains.get('m5-hair-hair'),1);
  assert.ok(preview.pending.some(p=>p.includes('原响应静止')));
});

test('unselected baked region can be muted without removing original topology',()=>{
  const {config,document,report}=fixture();config.hair.slots=['other'];
  const preview=jointAmplitudePreview(document,report,config);assert.equal(preview.gains.get('m5-hair-hair'),0);
  assert.equal(document.bones.length,4);
});

test('untrusted or incompatible helper names cannot change body tracks',()=>{
  const {config,document,report}=fixture();report.secondary.regions[0].helpers=['body','m5-hair-missing'];config.hair.strength=.5;
  const preview=jointAmplitudePreview(document,report,config);assert.equal(preview.gains.has('body'),false);
  assert.ok(preview.pending.some(p=>p.includes('不兼容')));
});

test('random seek and disabling preview restore the exact baked pose without cumulative drift',()=>{
  const {config,document,report}=fixture();config.hair.strength=.5;
  const preview=jointAmplitudePreview(document,report,config),setup=new Map(document.bones.map(b=>[b.name,b.rotation]));
  const frame=(time,gains)=>{const skeleton={bones:document.bones.map(b=>({data:{name:b.name},pose:{rotation:b.rotation+time*2}}))};
    applyJointAmplitude(skeleton,gains,setup);return skeleton.bones.map(b=>b.pose.rotation);};
  const first=frame(.7,preview.gains);frame(.2,preview.gains);frame(1,preview.gains);
  assert.deepEqual(frame(.7,preview.gains),first);assert.equal(first[0],21.4);assert.equal(first[1],30.7);
  assert.deepEqual(frame(.7,null),[21.4,31.4,31.4,31.4]);
  config.hair.strength=1;const reset=jointAmplitudePreview(document,report,config);
  assert.equal(reset.changed,false);assert.deepEqual(frame(.7,reset.gains),frame(.7,null));
});
