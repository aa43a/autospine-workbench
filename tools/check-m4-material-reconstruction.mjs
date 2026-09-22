// Isolate source, material decomposition, and clipping with the same official renderer.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [url,deps,chrome,receiptPath,segmentsPath,output,slot,frontPath,backPath]=process.argv.slice(2);
const receipt=JSON.parse(await fs.readFile(receiptPath));
const segmentRaw=await fs.readFile(segmentsPath),segments=JSON.parse(segmentRaw);
assert.equal(segments.parent,receipt.parent);
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
let contours=null,contourHashes=null;
if(frontPath||backPath){
  assert.ok(frontPath&&backPath);
  const raws=await Promise.all([frontPath,backPath].map(p=>fs.readFile(p)));contourHashes=raws.map(hash);
  const [front,back]=raws.map(r=>JSON.parse(r));
  assert.equal(front.candidate,receipt.parent);assert.equal(back.candidate,receipt.parent);
  assert.equal(back.side,'back');assert.equal(front.depth_sha256,back.depth_sha256);
  assert.equal(front.arm,slot);assert.equal(back.arm,slot);
  assert.deepEqual(front.rows.map(r=>r.time),back.rows.map(r=>r.time));
  contours=front.rows.map((r,i)=>({time:r.time,front:r.loops,back:back.rows[i].loops}));
}
const times=contours?contours.map(r=>r.time):[0,...segments.segments.flatMap((s,i)=>i?[s.start-1e-6,s.start,s.start+1e-6,(s.start+s.end)/2]:[(s.start+s.end)/2])];
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(new URL('after/runtime/player.html',url).href);
  await page.waitForFunction(()=>window.characterPlayerReady||window.characterPlayerError,null,{timeout:120000});
  assert.equal(await page.evaluate(()=>window.characterPlayerError),undefined);
  const rawScenes=await Promise.all(['before','after'].map(async label=>(await page.request.get(new URL(`${label}/runtime/player-assets/scene.json`,url).href)).body()));
  const [before,after]=rawScenes.map(raw=>JSON.parse(raw));
  assert.equal(before.artifact_sha256,receipt.parent);assert.equal(after.artifact_sha256,receipt.candidate);
  const runtime=await(await page.request.get(new URL('after/runtime/player-assets/runtime.js',url).href)).body();
  assert.equal(hash(runtime),receipt.runtime_sha256);
  const result=await page.evaluate(async({before,after,slot,times,contours})=>{
    function isolate(document,names){
      const doc=structuredClone(document);doc.slots=doc.slots.filter(s=>names.includes(s.name));
      doc.skins[0].attachments=Object.fromEntries(Object.entries(doc.skins[0].attachments).filter(([n])=>names.includes(n)));
      const anim=doc.animations['external-motion'];
      anim.attachments={default:Object.fromEntries(Object.entries(anim.attachments?.default??{}).filter(([n])=>names.includes(n)))};
      anim.slots=Object.fromEntries(Object.entries(anim.slots??{}).filter(([n])=>names.includes(n)));
      if(anim.drawOrder)throw Error('reconstruction_order_unsupported');
      doc.animations={'external-motion':anim};return doc;
    }
    const documents=[isolate(before.skeleton,[slot]),isolate(after.skeleton,['m4-root-material',slot]),
      isolate(after.skeleton,['m4-root-material','m4-clip-back',slot,'m4-clip-front','m4-front-mesh'])];
    const {left,bottom,width,height}=after.info;
    if(width*height>4194304)throw Error('reconstruction_camera_budget');
    const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
    const gl=canvas.getContext('webgl',{alpha:true,antialias:false,premultipliedAlpha:true,preserveDrawingBuffer:true});
    if(!gl)throw Error('reconstruction_webgl_missing');
    const atlas=new spine.TextureAtlas(after.atlas);
    await Promise.all(atlas.pages.map(async p=>{const image=new Image();image.src=after.textures[p.name];await image.decode();p.setTexture(new spine.GLTexture(gl,image,false,false));}));
    const renderer=new spine.SceneRenderer(canvas,gl);renderer.camera.setViewport(width,height);
    renderer.camera.position.x=left+width/2;renderer.camera.position.y=bottom+height/2;renderer.camera.update();
    function rig(doc){const data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(doc);return {skeleton:new spine.Skeleton(data),state:new spine.AnimationState(new spine.AnimationStateData(data))};}
    const rigs=documents.map(rig);
    function explicitRig(row){
      const doc=isolate(after.skeleton,['m4-root-material']);
      const original=after.skeleton.slots.find(s=>s.name===slot),mesh=after.skeleton.skins[0].attachments[slot][original.attachment];
      for(const side of ['back','front'])for(const [i,loop] of row[side].entries()){
        const name=`explicit-${side}-${i}`,clip=name+'-clip';
        doc.slots.push({name:clip,bone:'m4-clip-world',attachment:clip},{...original,name,attachment:name});
        doc.skins[0].attachments[clip]={[clip]:{type:'clipping',end:name,vertices:loop.points.flat(),vertexCount:loop.points.length,inverse:false}};
        doc.skins[0].attachments[name]={[name]:structuredClone(mesh)};
        const source=after.skeleton.animations['external-motion'].attachments.default[slot]?.[original.attachment];
        if(source)doc.animations['external-motion'].attachments.default[name]={[name]:structuredClone(source)};
      }
      return rig(doc);
    }
    function render(r,time){r.skeleton.setupPose();r.state.setAnimation(0,'external-motion',false);r.state.update(time);r.state.apply(r.skeleton);r.skeleton.updateWorldTransform(spine.Physics.update);
      gl.viewport(0,0,width,height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);renderer.begin();renderer.drawSkeleton(r.skeleton);renderer.end();
      const bytes=new Uint8Array(width*height*4);gl.readPixels(0,0,width,height,gl.RGBA,gl.UNSIGNED_BYTE,bytes);return bytes;}
    function compare(a,b){let count=0,maximum=0,alpha=0,missingOpaque=0;
      for(let i=0;i<a.length;i+=4){let delta=0;for(let c=0;c<4;c++)delta=Math.max(delta,Math.abs(a[i+c]-b[i+c]));
        if(delta>8)count++;maximum=Math.max(maximum,delta);alpha=Math.max(alpha,Math.abs(a[i+3]-b[i+3]));if(a[i+3]>=254&&b[i+3]<8)missingOpaque++;}
      return {over_eight:count,maximum_premultiplied_channel_difference:maximum,maximum_alpha_difference:alpha,missing_opaque_pixels:missingOpaque};}
    const rows=[];let visible=0;
    for(const [index,time] of times.entries()){const [a,b,c]=rigs.map(r=>render(r,time));
      if(time===0)for(let i=3;i<a.length;i+=4)if(a[i]>=8)visible++;
      rows.push({time,material:compare(a,b),clipping:compare(b,c),combined:compare(a,c),
        ...(contours?{explicit_complement:compare(b,render(explicitRig(contours[index]),time))}:{})});}
    const negative=rig(isolate(after.skeleton,[slot]));
    const negativeResult=compare(render(rigs[0],1.05),render(negative,1.05));
    const images=[];
    for(const time of [0,.85,1.05,2.4])for(const [index,r] of rigs.entries()){
      render(r,time);images.push({name:`${time}-${index}.png`,data:canvas.toDataURL('image/png').split(',')[1]});}
    return {rows,negative_control:negativeResult,visible,images,camera:{left,bottom,width,height}};
  },{before,after,slot,times,contours});
  assert.deepEqual(errors,[]);assert.ok(result.visible>0);assert.ok(result.negative_control.over_eight>0,'missing-root control did not expose error');
  await fs.mkdir(output,{recursive:false});
  result.image_inventory=[];
  for(const image of result.images){const bytes=Buffer.from(image.data,'base64');await fs.writeFile(path.join(output,image.name),bytes);result.image_inventory.push({name:image.name,sha256:hash(bytes)});}
  delete result.images;
  Object.assign(result,{authority:'none',selected:false,scope:'isolated_arm_native_framebuffer_samples_not_character_occlusion_acceptance',candidate:receipt.candidate,parent:receipt.parent,
    runtime_sha256:hash(runtime),scene_sha256:rawScenes.map(hash),segments_sha256:hash(segmentRaw),contour_sha256:contourHashes,
    explicit_scope:contours?'independent_static_skeleton_per_source_sample_not_animation_timeline':null,errors});
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify({frames:result.rows.length,material_max:Math.max(...result.rows.map(r=>r.material.maximum_alpha_difference)),clipping_max:Math.max(...result.rows.map(r=>r.clipping.maximum_alpha_difference)),
    explicit_max:contours?Math.max(...result.rows.map(r=>r.explicit_complement.maximum_alpha_difference)):null,negative_control:result.negative_control}));
} finally {await browser.close();}
