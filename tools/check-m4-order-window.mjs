// Verify the serialized Spine order track, not just a manually reordered screenshot.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [fixturePath,candidateFolder,deps,chrome,output]=process.argv.slice(2),hash=b=>createHash('sha256').update(b).digest('hex');
const fixtureRaw=await fs.readFile(fixturePath),fixture=JSON.parse(fixtureRaw);
const receiptRaw=await fs.readFile(path.join(candidateFolder,'report.json')),receipt=JSON.parse(receiptRaw);
const candidateRaw=await fs.readFile(path.join(candidateFolder,'skeleton.json')),candidate=JSON.parse(candidateRaw);
assert.equal(hash(fixtureRaw),receipt.fixture_sha256);assert.equal(hash(candidateRaw),receipt.skeleton_sha256);
const keys=candidate.animations['external-motion'].drawOrder;
const expected=structuredClone(fixture.skeleton);expected.animations['external-motion'].drawOrder=keys;
assert.deepEqual(candidate,expected);assert.equal(keys.length,2);
assert.equal(keys[0].time,receipt.window.start);assert.equal(keys[1].time,receipt.window.end);
assert.deepEqual(keys[1].offsets,[]);
const slots=fixture.skeleton.slots.map(s=>s.name),active=[...slots];active.splice(active.indexOf(receipt.window.region),1);
active.splice(active.indexOf(receipt.window.after_slot)+1,0,receipt.window.region);
assert.deepEqual(keys[0].offsets,slots.map((slot,i)=>({slot,offset:active.indexOf(slot)-i})));
const boundaryTimes=new Set();
for(const time of [receipt.window.start,receipt.window.end,...keys.map(k=>Math.fround(k.time))])
  for(const delta of [-.004,-.001,-.0001,-.000001,0,.000001,.0001,.001,.004])boundaryTimes.add(time+delta);
const times=[...new Set([...fixture.rows.map(r=>r.time),...boundaryTimes])].sort((a,b)=>a-b);
const runtime=await fs.readFile(path.resolve(deps,'node_modules/@esotericsoftware/spine-webgl/dist/iife/spine-webgl.js'));
assert.equal(hash(runtime),fixture.runtime_sha256);
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
  page.on('console',m=>{if(m.text().startsWith('window frames '))console.log(m.text());});
  await page.setContent('<!doctype html><title>Local Spine order window test</title>');
  await page.addScriptTag({content:runtime.toString()});
  const result=await page.evaluate(async({skeleton,atlasText,textures,info,keys,times,active,window})=>{
    const {width,height,left,bottom}=info,canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
    const gl=canvas.getContext('webgl',{alpha:true,antialias:false,premultipliedAlpha:true,preserveDrawingBuffer:true});
    if(!gl)throw Error('window_webgl_missing');
    const atlas=new spine.TextureAtlas(atlasText);
    await Promise.all(atlas.pages.map(async p=>{const im=new Image();im.src=textures[p.name];await im.decode();p.setTexture(new spine.GLTexture(gl,im,false,false));}));
    const reader=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas));
    const baseData=reader.readSkeletonData(skeleton);skeleton.animations['external-motion'].drawOrder=keys;
    const candidateData=reader.readSkeletonData(skeleton),renderer=new spine.SceneRenderer(canvas,gl);
    renderer.camera.setViewport(width,height);renderer.camera.position.x=left+width/2;renderer.camera.position.y=bottom+height/2;renderer.camera.update();
    function pose(data,t){const rig=new spine.Skeleton(data),state=new spine.AnimationState(new spine.AnimationStateData(data));
      rig.setupPose();state.setAnimation(0,'external-motion',false);state.update(t);state.apply(rig);rig.updateWorldTransform(spine.Physics.update);return rig;}
    function render(rig){gl.viewport(0,0,width,height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
      renderer.begin();renderer.drawSkeleton(rig);renderer.end();const pixels=new Uint8Array(width*height*4);
      gl.readPixels(0,0,width,height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);if(gl.getError()!==gl.NO_ERROR)throw Error('window_read_failed');return pixels;}
    const rows=[],setup=baseData.slots.map(s=>s.name),start=Math.fround(window.start),end=Math.fround(window.end);
    for(const time of times){
      const base=pose(baseData,time),next=pose(candidateData,time),inside=time>=start&&time<end;
      const order=next.drawOrder.appliedPose.map(s=>s.data.name);
      if(JSON.stringify(order)!==JSON.stringify(inside?active:setup))throw Error('window_serialized_order_mismatch:'+time);
      let vertexDelta=0;
      for(let i=0;i<base.slots.length;i++){
        const a=base.slots[i],b=next.slots[i],aa=a.appliedPose.attachment,bb=b.appliedPose.attachment;
        if(aa.name!==bb.name||aa.worldVerticesLength!==bb.worldVerticesLength)throw Error('window_attachment_changed');
        const va=new Float32Array(aa.worldVerticesLength),vb=new Float32Array(bb.worldVerticesLength);
        aa.computeWorldVertices(base,a,0,va.length,va,0,2);bb.computeWorldVertices(next,b,0,vb.length,vb,0,2);
        for(let j=0;j<va.length;j++)vertexDelta=Math.max(vertexDelta,Math.abs(va[j]-vb[j]));
      }
      if(vertexDelta!==0)throw Error('window_geometry_changed');
      const a=render(base),b=render(next);let changed=0,alpha=0,maximum=0,alphaMax=0,gaps=0;
      for(let i=0;i<a.length;i+=4){let d=0;for(let c=0;c<4;c++)d=Math.max(d,Math.abs(a[i+c]-b[i+c]));
        if(d>1)changed++;if(a[i+3]!==b[i+3])alpha++;maximum=Math.max(maximum,d);
        alphaMax=Math.max(alphaMax,Math.abs(a[i+3]-b[i+3]));if(a[i+3]>=8&&b[i+3]<8)gaps++;}
      if(!inside&&maximum!==0)throw Error('window_outside_pixels_changed:'+time);
      rows.push({time,inside,changed_pixels:changed,alpha_changed_pixels:alpha,maximum_alpha_delta:alphaMax,
        newly_below_alpha_eight:gaps,maximum_channel_delta:maximum,vertex_delta:vertexDelta});
      if(rows.length%16===0)console.log('window frames '+rows.length+'/'+times.length);
    }
    const switches=[];
    for(const time of [start,end]){
      const rig=pose(candidateData,time),byName=Object.fromEntries(rig.slots.map(s=>[s.data.name,s]));
      rig.drawOrder.appliedPose=setup.map(n=>byName[n]);const original=render(rig);
      rig.drawOrder.appliedPose=active.map(n=>byName[n]);const alternate=render(rig);
      let changed=0,maximum=0;
      for(let i=0;i<original.length;i+=4){let delta=0;for(let c=0;c<4;c++)delta=Math.max(delta,Math.abs(original[i+c]-alternate[i+c]));
        if(delta>1)changed++;maximum=Math.max(maximum,delta);}
      switches.push({time,changed_pixels:changed,maximum_channel_delta:maximum,scope:'same_pose_two_orders_at_stored_key'});
    }
    gl.getExtension('WEBGL_lose_context')?.loseContext();return {rows,switches,stored_window:{start,end}};
  },{skeleton:fixture.skeleton,atlasText:fixture.atlas,textures:fixture.textures,info:fixture.info,keys,times,active,window:receipt.window});
  assert.deepEqual(errors,[]);
  const near=result.rows.filter(r=>boundaryTimes.has(r.time));
  Object.assign(result,{fixture_sha256:hash(fixtureRaw),candidate_sha256:hash(candidateRaw),receipt_sha256:hash(receiptRaw),
    runtime_sha256:hash(runtime),runtime_version:fixture.runtime_version,tool_sha256:hash(await fs.readFile(new URL(import.meta.url))),
    boundary_samples:near.length,boundary_changed_frames:near.filter(r=>r.maximum_channel_delta!==0).length,
    switch_sample_status:result.switches.every(r=>r.changed_pixels===0)?'no_change_over_one_channel_unit':'visible_switch_difference',
    scope:'serialized_order_source_midpoints_and_dense_switch_probes_not_continuous_geometry_acceptance',
    selected:false,authority:'none',production_authorized:false});
  await fs.writeFile(output,JSON.stringify(result,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({frames:result.rows.length,boundary_samples:result.boundary_samples,boundary_changed_frames:result.boundary_changed_frames,
    changed_frames:result.rows.filter(r=>r.changed_pixels).length,alpha_changed_frames:result.rows.filter(r=>r.alpha_changed_pixels).length,
    alpha_max:Math.max(...result.rows.map(r=>r.maximum_alpha_delta)),new_gap_samples:result.rows.reduce((n,r)=>n+r.newly_below_alpha_eight,0),switches:result.switches}));
}finally{await browser.close();}
