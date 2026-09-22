// Real animated ordinary clips: isolated reconstruction at keys and between keys.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [url,deps,chrome,folder,fieldPath]=process.argv.slice(2);
const hash=b=>createHash('sha256').update(b).digest('hex');
const receipt=JSON.parse(await fs.readFile(path.join(folder,'report.json')));
const fieldRaw=await fs.readFile(fieldPath),field=JSON.parse(fieldRaw);
assert.equal(field.candidate,receipt.parent);
const times=field.rows.flatMap((r,i)=>i?[(field.rows[i-1].time+r.time)/2,r.time]:[r.time]);
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
 const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.goto(new URL('after/runtime/player.html',url).href);
 await page.waitForFunction(()=>window.characterPlayerReady||window.characterPlayerError,null,{timeout:120000});
 assert.equal(await page.evaluate(()=>window.characterPlayerError),undefined);
 const raws=await Promise.all(['before','after'].map(async name=>(await page.request.get(new URL(`${name}/runtime/player-assets/scene.json`,url).href)).body()));
 const [before,after]=raws.map(r=>JSON.parse(r));
 assert.equal(before.artifact_sha256,receipt.parent);assert.equal(after.artifact_sha256,receipt.candidate);
 const runtime=await(await page.request.get(new URL('after/runtime/player-assets/runtime.js',url).href)).body();
 assert.equal(hash(runtime),receipt.runtime_sha256);
 assert.deepEqual(before.textures,after.textures);assert.equal(before.atlas,after.atlas);
 const result=await page.evaluate(async({before,after,times,arm})=>{
  function isolate(source,names){
   const doc=structuredClone(source);doc.slots=doc.slots.filter(s=>names.includes(s.name));
   doc.skins[0].attachments=Object.fromEntries(Object.entries(doc.skins[0].attachments).filter(([n])=>names.includes(n)));
   const anim=doc.animations['external-motion'];
   anim.attachments={default:Object.fromEntries(Object.entries(anim.attachments?.default??{}).filter(([n])=>names.includes(n)))};
   anim.slots=Object.fromEntries(Object.entries(anim.slots??{}).filter(([n])=>names.includes(n)));
   if(anim.drawOrder)throw Error('unexpected draw order');doc.animations={'external-motion':anim};return doc;
  }
  const docs=[isolate(before.skeleton,[arm]),isolate(after.skeleton,after.skeleton.slots.filter(s=>s.name.startsWith('m4-tri-')).map(s=>s.name))];
  const {left,bottom,width,height}=after.info;if(width*height>4194304)throw Error('camera budget');
  const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
  const gl=canvas.getContext('webgl',{alpha:true,antialias:false,premultipliedAlpha:true,preserveDrawingBuffer:true});
  const atlas=new spine.TextureAtlas(after.atlas);
  await Promise.all(atlas.pages.map(async p=>{const image=new Image();image.src=after.textures[p.name];await image.decode();p.setTexture(new spine.GLTexture(gl,image,false,false));}));
  const renderer=new spine.SceneRenderer(canvas,gl);renderer.camera.setViewport(width,height);
  renderer.camera.position.x=left+width/2;renderer.camera.position.y=bottom+height/2;renderer.camera.update();
  function rig(doc){const data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(doc);return {skeleton:new spine.Skeleton(data),state:new spine.AnimationState(new spine.AnimationStateData(data))};}
  const rigs=docs.map(rig);
  function render(r,time){r.skeleton.setupPose();r.state.setAnimation(0,'external-motion',false);r.state.update(time);r.state.apply(r.skeleton);r.skeleton.updateWorldTransform(spine.Physics.update);
   gl.viewport(0,0,width,height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);renderer.begin();renderer.drawSkeleton(r.skeleton);renderer.end();
   const bytes=new Uint8Array(width*height*4);gl.readPixels(0,0,width,height,gl.RGBA,gl.UNSIGNED_BYTE,bytes);return bytes;}
  function difference(a,b){let over8=0,missing=0,maximum=0;for(let i=0;i<a.length;i+=4){let delta=0;for(let c=0;c<4;c++)delta=Math.max(delta,Math.abs(a[i+c]-b[i+c]));if(delta>8)over8++;if(a[i+3]>=254&&b[i+3]<8)missing++;maximum=Math.max(maximum,delta);}return {over8,missing,maximum};}
  const rows=[],start=performance.now();
  for(const time of times)rows.push({time,...difference(...rigs.map(r=>render(r,time)))});
  const negative=rig(isolate(after.skeleton,[]));const control=difference(render(rigs[0],1.05),render(negative,1.05));
  const forward=render(rigs[1],0);render(rigs[1],4);const reverse=difference(forward,render(rigs[1],0));
  const images=[];for(const time of [0,.7,1.05,2.4])for(const [index,r] of rigs.entries()){render(r,time);images.push({name:`${time}-${index}.png`,data:canvas.toDataURL('image/png').split(',')[1]});}
  return {rows,control,reverse,elapsed_ms:performance.now()-start,images,slots:docs[1].slots.length};
 },{before,after,times,arm:field.arm});
 assert.deepEqual(errors,[]);assert.ok(result.control.missing>0);assert.equal(result.reverse.maximum,0);
 const output=path.join(folder,'reconstruction');await fs.mkdir(output,{recursive:false});
 result.image_inventory=[];for(const image of result.images){const bytes=Buffer.from(image.data,'base64');await fs.writeFile(path.join(output,image.name),bytes);result.image_inventory.push({name:image.name,sha256:hash(bytes)});}delete result.images;
 Object.assign(result,{authority:'none',selected:false,parent:receipt.parent,candidate:receipt.candidate,field_sha256:hash(fieldRaw),scene_sha256:raws.map(hash),runtime_sha256:hash(runtime),scope:'animated_isolated_arm_samples_not_full_character_visual_acceptance'});
 await fs.writeFile(path.join(output,'report.json'),JSON.stringify(result,null,2));
 console.log(JSON.stringify({samples:result.rows.length,missing:Math.max(...result.rows.map(r=>r.missing)),over8:Math.max(...result.rows.map(r=>r.over8)),maximum:Math.max(...result.rows.map(r=>r.maximum)),slots:result.slots,elapsed_ms:result.elapsed_ms}));
} finally {await browser.close();}
