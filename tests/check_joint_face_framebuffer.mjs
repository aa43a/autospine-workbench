// Actual official WebGL face captures; visual acceptance remains a separate decision.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const [fixtures, output, runtime, dependencies, artifactRoot] = process.argv.slice(2);
const {chromium} = await import(pathToFileURL(path.resolve(dependencies, 'node_modules/playwright-core/index.mjs')));
await fs.mkdir(output, {recursive:true});
const browser = await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless:true, args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const rows=[];
try {
  for (const name of ['alice', 'huiye', 'hongmeiling']) {
    const source=JSON.parse(await fs.readFile(path.join(fixtures,name+'.json')));
    const atlasPages=source.atlas.split(/\r?\n\r?\n/).map(s=>s.trim().split(/\r?\n/)[0]).filter(Boolean);
    source.textures=Object.fromEntries(await Promise.all(atlasPages.map(async p=>[p,'data:image/png;base64,'+
      (source.texture_updates?.[p] || (await fs.readFile(path.join(artifactRoot,source.source,p))).toString('base64'))])));
    const page=await browser.newPage({viewport:{width:1200,height:800}}),errors=[];
    page.on('pageerror',e=>errors.push(String(e)));
    await page.setContent('<!doctype html><canvas></canvas>');
    await page.addScriptTag({path:runtime});
    const captures=await page.evaluate(async source=>{
      const canvas=document.querySelector('canvas');canvas.width=600;canvas.height=600;
      const gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:true,antialias:false,preserveDrawingBuffer:true});
      if(!gl)throw Error('webgl_missing');
      const atlas=new spine.TextureAtlas(source.atlas);
      await Promise.all(atlas.pages.map(async p=>{const image=new Image();image.src=source.textures[p.name];await image.decode();p.setTexture(new spine.GLTexture(gl,image,false,false));}));
      const data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(source.skeleton);
      const rig=new spine.Skeleton(data),state=new spine.AnimationState(new spine.AnimationStateData(data));
      const entry=state.setAnimation(0,source.animation,false),renderer=new spine.SceneRenderer(canvas,gl);
      const slots=new Set(source.report.affected_slots),all=[];
      rig.setupPose();state.apply(rig);rig.updateWorldTransform(spine.Physics.update);
      for(const slot of rig.slots)if(slots.has(slot.data.name)){
        const a=slot.appliedPose.attachment,v=new Float32Array(a.worldVerticesLength);a.computeWorldVertices(rig,slot,0,v.length,v,0,2);
        for(let i=0;i<v.length;i+=2)all.push([v[i],v[i+1]]);
      }
      const xs=all.map(p=>p[0]),ys=all.map(p=>p[1]);
      const left=Math.min(...xs)-28,right=Math.max(...xs)+28,bottom=Math.min(...ys)-28,top=Math.max(...ys)+28;
      const size=Math.max(right-left,top-bottom);renderer.camera.setViewport(size,size);
      renderer.camera.position.x=(left+right)/2;renderer.camera.position.y=(bottom+top)/2;renderer.camera.update();
      const results=[];let closedPixels=null;
      for(const [label,time,hide] of [['open',0,false],['expression-half',.5,false],['closed',.59,false],['reopened',.75,false],['expression',1,false],['underlay',0,true],['closed-reverse',.59,false]]){
        rig.setupPose();entry.trackTime=time;state.apply(rig);rig.updateWorldTransform(spine.Physics.update);
        if(hide)for(const slot of rig.slots)if(slots.has(slot.data.name))slot.appliedPose.color.a=0;
        gl.viewport(0,0,600,600);gl.clearColor(.18,.21,.24,1);gl.clear(gl.COLOR_BUFFER_BIT);
        renderer.begin();renderer.drawSkeleton(rig);renderer.end();
        const pixels=new Uint8Array(600*600*4);gl.readPixels(0,0,600,600,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
        if(label==='closed')closedPixels=pixels;
        const reverseMatch=label==='closed-reverse'?pixels.every((v,i)=>v===closedPixels[i]):null;
        results.push({label,time,hidden_face_parts:hide,png:canvas.toDataURL(),reverseMatch});
      }
      return results;
    },source);
    assert.deepEqual(errors,[]);
    assert.equal(captures.find(r=>r.label==='closed-reverse').reverseMatch,true);
    for(const capture of captures){await fs.writeFile(path.join(output,`${name}-${capture.label}.png`),Buffer.from(capture.png.split(',')[1],'base64'));}
    rows.push({name,source:source.source,captures:captures.map(({label,time,hidden_face_parts})=>({label,time,hidden_face_parts})),
      reverse_framebuffer_exact:true,errors});
    await page.close();
  }
} finally {await browser.close();}
await fs.writeFile(path.join(output,'report.json'),JSON.stringify({passed:true,scope:'official_webgl_face_captures',rows,
  visual_acceptance:'not_evaluated'},null,2));
console.log(JSON.stringify({passed:true,rows}));
