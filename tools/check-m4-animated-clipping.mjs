// Official Runtime capability proof. Synthetic clip motion is not inferred garment depth.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [url,deps,chrome,output,slot,expectedArtifact]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
  const page=await browser.newPage();await page.goto(url);
  await page.waitForFunction(()=>window.characterPlayerReady||window.characterPlayerError,null,{timeout:120000});
  assert.equal(await page.evaluate(()=>window.characterPlayerError),undefined);
  const sceneRaw=await(await page.request.get(new URL('player-assets/scene.json',url).href)).body();
  const scene=JSON.parse(sceneRaw);assert.equal(scene.artifact_sha256,expectedArtifact);
  const runtimeRaw=await(await page.request.get(new URL('player-assets/runtime.js',url).href)).body();
  const result=await page.evaluate(async({scene,slot})=>{
    const original=scene.skeleton, sourceSlot=original.slots.find(s=>s.name===slot);
    if(!sourceSlot)throw Error('proof_slot_missing');
    const mesh=original.skins[0].attachments[slot][sourceSlot.attachment];
    if(mesh.type!=='mesh'||original.animations['external-motion'].drawOrder)throw Error('proof_source_unsupported');
    const baseline=structuredClone(original);baseline.slots=[structuredClone(sourceSlot)];
    baseline.skins=[{name:'default',attachments:{[slot]:{[sourceSlot.attachment]:structuredClone(mesh)}}}];
    const anim=baseline.animations['external-motion'];
    const sourceDeform=anim.attachments?.default?.[slot];
    anim.attachments={default:sourceDeform?{[slot]:sourceDeform}:{}};
    delete anim.slots;
    baseline.animations={'external-motion':anim};
    const candidate=structuredClone(baseline);candidate.bones.push({name:'clip-world'});
    candidate.slots=[];candidate.skins[0].attachments={};candidate.animations['external-motion'].attachments={default:{}};
    const {left,bottom,width,height}=scene.info, x0=left, x1=left+width;
    const polygon=x=>[left-width,bottom-height,x,bottom-height,x,bottom+height*2,left-width,bottom+height*2];
    const setup=polygon(x0);
    for(const side of ['back','front']) {
      const clip='proof-clip-'+side,copy='proof-'+side;
      candidate.slots.push({name:clip,bone:'clip-world',attachment:clip},{...sourceSlot,name:copy,attachment:copy});
      candidate.skins[0].attachments[clip]={[clip]:{type:'clipping',end:copy,vertexCount:4,vertices:setup,inverse:side==='back',convex:true}};
      candidate.skins[0].attachments[copy]={[copy]:{...structuredClone(mesh),path:mesh.path??sourceSlot.attachment}};
      const tracks=candidate.animations['external-motion'].attachments.default;
      if(sourceDeform)tracks[copy]={[copy]:structuredClone(sourceDeform[sourceSlot.attachment])};
      tracks[clip]={[clip]:{deform:[{time:0,vertices:Array(8).fill(0)},{time:4,vertices:polygon(x1).map((v,i)=>v-setup[i])}]}};
    }
    const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
    const gl=canvas.getContext('webgl',{alpha:true,antialias:false,premultipliedAlpha:true,preserveDrawingBuffer:true});
    if(!gl)throw Error('proof_webgl_missing');
    const atlas=new spine.TextureAtlas(scene.atlas);
    await Promise.all(atlas.pages.map(async p=>{const image=new Image();image.src=scene.textures[p.name];await image.decode();p.setTexture(new spine.GLTexture(gl,image,false,false));}));
    const renderer=new spine.SceneRenderer(canvas,gl);renderer.camera.setViewport(width,height);
    renderer.camera.position.x=left+width/2;renderer.camera.position.y=bottom+height/2;renderer.camera.update();
    function rig(doc){const data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(doc);return {skeleton:new spine.Skeleton(data),state:new spine.AnimationState(new spine.AnimationStateData(data))};}
    const a=rig(baseline),b=rig(candidate);
    function render(r,time){r.skeleton.setupPose();r.state.setAnimation(0,'external-motion',false);r.state.update(time);r.state.apply(r.skeleton);r.skeleton.updateWorldTransform(spine.Physics.update);
      gl.viewport(0,0,width,height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);renderer.begin();renderer.drawSkeleton(r.skeleton);renderer.end();
      const pixels=new Uint8Array(width*height*4);gl.readPixels(0,0,width,height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);return pixels;}
    const rows=[];
    for(const time of [0,.5,1,1.3,1.5,2,2.5,3,3.5,4,0]){
      const original=render(a,time),split=render(b,time);let changed=0,max=0,alpha=0;
      for(let i=0;i<original.length;i+=4){let delta=0;for(let c=0;c<4;c++)delta=Math.max(delta,Math.abs(original[i+c]-split[i+c]));if(delta)changed++;max=Math.max(max,delta);if(original[i+3]!==split[i+3])alpha++;}
      const clip=b.skeleton.findSlot('proof-clip-front');
      rows.push({time,changed_pixels:changed,max_channel_difference:max,alpha_changed_pixels:alpha,clip_deform:Array.from(clip.pose.deform)});
    }
    const broken=structuredClone(candidate);broken.skins[0].attachments['proof-clip-back']['proof-clip-back'].inverse=false;
    const negative=render(rig(broken),1.3),reference=render(a,1.3);
    let negativeChanged=0,visible=0;
    for(let i=0;i<negative.length;i+=4){if(reference[i+3])visible++;if([0,1,2,3].some(c=>Math.abs(negative[i+c]-reference[i+c])>8))negativeChanged++;}
    return {rows,candidate,width,height,negative_control_changed_pixels:negativeChanged,reference_visible_pixels:visible,
      authority:'none',selected:false,scope:'synthetic_complementary_clipping_capability_not_real_depth_or_character_acceptance'};
  },{scene,slot});
  assert.ok(result.rows.some(r=>JSON.stringify(r.clip_deform)!==JSON.stringify(result.rows[0].clip_deform)),'clip deform did not animate');
  assert.deepEqual(result.rows.at(-1).clip_deform,result.rows[0].clip_deform,'reverse seek did not restore clipping');
  assert.ok(result.reference_visible_pixels>0&&result.negative_control_changed_pixels>0,'negative control did not expose broken complementary clipping');
  result.parent=expectedArtifact;result.scene_sha256=createHash('sha256').update(sceneRaw).digest('hex');
  result.runtime_sha256=createHash('sha256').update(runtimeRaw).digest('hex');
  await fs.mkdir(output,{recursive:true});
  await fs.writeFile(path.join(output,'skeleton-proof.json'),JSON.stringify(result.candidate));delete result.candidate;
  result.exact_reconstruction=result.rows.every(r=>r.changed_pixels===0);
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser.close();}
