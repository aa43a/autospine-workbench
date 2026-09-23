// Same-artwork regression across hard switches, in the actual official WebGL renderer.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [base,parent,job,output,deps]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
 const page=await browser.newPage();await page.goto(`${base}/api/motions/${job}/view/player.html`);
 await page.waitForFunction(()=>window.characterPlayerReady||window.characterPlayerError,null,{timeout:120000});
 assert.equal(await page.evaluate(()=>window.characterPlayerError),undefined);
 const scenes=await Promise.all([parent,job].map(async id=>{const r=await page.request.get(`${base}/api/motions/${id}/view/player-assets/scene.json`);assert.equal(r.status(),200);return r.json();}));
 const report=await page.evaluate(async([before,after])=>{
  const {left,bottom,width,height}=after.info;if(width*height>4194304)throw Error('camera_budget');
  const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
  const gl=canvas.getContext('webgl',{alpha:true,antialias:false,premultipliedAlpha:true,preserveDrawingBuffer:true});if(!gl)throw Error('no_webgl');
  const atlas=new spine.TextureAtlas(after.atlas);
  await Promise.all(atlas.pages.map(async p=>{const image=new Image();image.src=after.textures[p.name];await image.decode();p.setTexture(new spine.GLTexture(gl,image,false,false));}));
  const renderer=new spine.SceneRenderer(canvas,gl);renderer.camera.setViewport(width,height);renderer.camera.position.x=left+width/2;renderer.camera.position.y=bottom+height/2;renderer.camera.update();
  const rigs=[before,after].map(scene=>{const data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(scene.skeleton);return {skeleton:new spine.Skeleton(data),state:new spine.AnimationState(new spine.AnimationStateData(data))};});
  function render(r,time){r.skeleton.setupPose();r.state.setAnimation(0,'external-motion',false);r.state.update(time);r.state.apply(r.skeleton);r.skeleton.updateWorldTransform(spine.Physics.update);gl.viewport(0,0,width,height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);renderer.begin();renderer.drawSkeleton(r.skeleton);renderer.end();const bytes=new Uint8Array(width*height*4);gl.readPixels(0,0,width,height,gl.RGBA,gl.UNSIGNED_BYTE,bytes);return bytes;}
  const rows=[];
  for(const time of [0,.9999,1,1.0001,1.5,1.9999,2,2.0001,3.966667]){
   const a=render(rigs[0],time),b=render(rigs[1],time);let maximum=0,changed=0,overEight=0,missingOpaque=0;
   for(let i=0;i<a.length;i+=4){let difference=0;for(let k=0;k<4;k++)difference=Math.max(difference,Math.abs(a[i+k]-b[i+k]));maximum=Math.max(maximum,difference);changed+=difference>0;overEight+=difference>8;missingOpaque+=a[i+3]>=254&&b[i+3]<8;}
   rows.push({time,maximum,changed,overEight,missingOpaque});
  }
  return {parent:before.artifact_sha256,candidate:after.artifact_sha256,rows,camera:{left,bottom,width,height},scope:'same_artwork_switch_regression_not_new_artwork_acceptance'};
 },scenes);
 await fs.writeFile(output,JSON.stringify(report));console.log(JSON.stringify(report));
}finally{await browser.close();}
