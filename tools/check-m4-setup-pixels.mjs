// Render exact source assets at setup through the official player Runtime.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [url,dependencies,chrome,output]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
  const page=await browser.newPage();await page.goto(url);
  const inventory=await(await page.request.get(new URL('comparison.json',url).href)).json();
  assert.equal(inventory.rows.length,1);const images=[];
  await fs.mkdir(output,{recursive:true});
  for(const [index,view] of inventory.rows[0].views.entries()){
    await page.goto(new URL(view.url,url).href);
    await page.waitForFunction(()=>window.characterPlayerReady||window.characterPlayerError,null,{timeout:120000});
    assert.equal(await page.evaluate(()=>window.characterPlayerError),undefined);
    const result=await page.evaluate(async()=>{
      const scene=await(await fetch(new URL('player-assets/scene.json',location.href))).json();
      const canvas=document.createElement('canvas');canvas.width=scene.info.width;canvas.height=scene.info.height;
      const gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:true,antialias:false,preserveDrawingBuffer:true});
      if(!gl)throw Error('setup_webgl_missing');
      const atlas=new spine.TextureAtlas(scene.atlas);
      await Promise.all(atlas.pages.map(async p=>{const image=new Image();image.src=scene.textures[p.name];await image.decode();p.setTexture(new spine.GLTexture(gl,image,false,false));}));
      const data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(scene.skeleton);
      const skeleton=new spine.Skeleton(data);skeleton.setupPose();skeleton.updateWorldTransform(spine.Physics.update);
      const renderer=new spine.SceneRenderer(canvas,gl);const {width,height,left,bottom}=scene.info;
      renderer.camera.setViewport(width,height);renderer.camera.position.x=left+width/2;renderer.camera.position.y=bottom+height/2;renderer.camera.update();
      gl.viewport(0,0,width,height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
      renderer.begin();renderer.drawSkeleton(skeleton);renderer.end();
      const pixels=new Uint8Array(width*height*4);gl.readPixels(0,0,width,height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
      return {artifact:scene.artifact_sha256,width,height,left,bottom,pixels:Array.from(pixels),png:canvas.toDataURL()};
    });
    assert.equal(result.artifact,view.artifact);
    await fs.writeFile(path.join(output,`setup-${index}.png`),Buffer.from(result.png.split(',')[1],'base64'));
    images.push(result);
  }
  const [a,b]=images;
  for(const key of ['width','height','left','bottom'])assert.equal(a[key],b[key]);
  let differentPixels=0,maxChannelDifference=0,alphaDifferences=0;
  for(let i=0;i<a.pixels.length;i+=4){
    let changed=false;
    for(let c=0;c<4;c++){const d=Math.abs(a.pixels[i+c]-b.pixels[i+c]);maxChannelDifference=Math.max(maxChannelDifference,d);changed ||= d>0;}
    differentPixels+=Number(changed);alphaDifferences+=Number(a.pixels[i+3]!==b.pixels[i+3]);
  }
  const report={authority:'none',scope:'same_camera_official_runtime_setup_pixels_only',artifacts:images.map(i=>i.artifact),
    width:a.width,height:a.height,differentPixels,alphaDifferences,maxChannelDifference,exactlyEqual:differentPixels===0};
  await fs.writeFile(path.join(output,'setup-check.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}finally{await browser.close();}
