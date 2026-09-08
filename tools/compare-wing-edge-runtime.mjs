// Same-canvas official Runtime comparison. Measures changes, not visual approval.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [beforeURL,afterURL,output,dependencies,chrome,mode]=process.argv.slice(2);
if(mode&&!['--slot-order-only','--all-frames'].includes(mode))throw new Error('comparison_mode');
for(const value of [beforeURL,afterURL]){
  const url=new URL(value);if(url.hostname!=='127.0.0.1'||url.protocol!=='http:')throw new Error('local_preview_required');
}
const hash=raw=>crypto.createHash('sha256').update(raw).digest('hex');
const {chromium}=await import(pathToFileURL(path.join(dependencies,'node_modules/playwright-core/index.mjs')));
await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
  const pages=[];const identities=[];
  for(const url of [beforeURL,afterURL]){
    const page=await browser.newPage({viewport:{width:1100,height:1100}});await page.goto(url);
    await page.waitForFunction(()=>window.ready||window.failure,{},{timeout:60000});
    if(await page.evaluate(()=>window.failure))throw new Error('runtime_load_failed');
    const identity={};
    for(const [key,file] of [['runtime','/runtime.js'],['skeleton','/crino/skeleton.json'],['manifest','/crino/preview-manifest.json']]){
      const response=await page.request.get(new URL(file,url).href);if(!response.ok())throw new Error('identity_fetch_failed');const raw=await response.body();identity[key]=hash(raw);
      if(key==='skeleton'&&mode==='--slot-order-only'){const doc=JSON.parse(raw);doc.slots.sort((a,b)=>a.name.localeCompare(b.name));identity.order_normalized_skeleton=hash(JSON.stringify(doc));}
    }
    identities.push(identity);pages.push(page);
  }
  const sameSkeleton=mode==='--slot-order-only'?identities[0].order_normalized_skeleton===identities[1].order_normalized_skeleton:identities[0].skeleton===identities[1].skeleton;
  if(identities[0].runtime!==identities[1].runtime||!sameSkeleton)throw new Error('comparison_identity_mismatch');
  const samples=[];
  const times=mode==='--all-frames'?Array.from({length:121},(_,i)=>i/60):[0,.5,1,1.5,2];
  for(const time of times){
    const captures=[];
    for(const [i,page] of pages.entries()){
      const capture=await page.evaluate(t=>{
        window.renderAt(t);const canvas=document.querySelector('canvas'),gl=canvas.getContext('webgl');
        const bytes=new Uint8Array(canvas.width*canvas.height*4);gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,bytes);
        let binary='';for(let offset=0;offset<bytes.length;offset+=32768)binary+=String.fromCharCode(...bytes.subarray(offset,offset+32768));
        return {width:canvas.width,height:canvas.height,pixels:btoa(binary)};
      },time);
      const name=(mode!=='--all-frames'||[0,15,20,27,30,60,89,90,120].includes(Math.round(time*60)))?(i?'after':'before')+'-'+time+'.png':null;
      if(name)await page.locator('canvas').screenshot({path:path.join(output,name)});
      captures.push({...capture,pixels:Buffer.from(capture.pixels,'base64'),file:name});
    }
    const [a,b]=captures;if(a.width!==b.width||a.height!==b.height)throw new Error('comparison_canvas_mismatch');
    let changed=0,max=0,alphaThresholdLoss=0,alphaThresholdGain=0;
    for(let i=0;i<a.pixels.length;i+=4){
      let delta=0;for(let c=0;c<4;c++)delta=Math.max(delta,Math.abs(a.pixels[i+c]-b.pixels[i+c]));
      max=Math.max(max,delta);changed+=delta>0;
      alphaThresholdLoss+=a.pixels[i+3]>=8&&b.pixels[i+3]<8;
      alphaThresholdGain+=a.pixels[i+3]<8&&b.pixels[i+3]>=8;
    }
    samples.push({time,changed_pixels:changed,max_channel_delta:max,alpha8_loss_pixels:alphaThresholdLoss,alpha8_gain_pixels:alphaThresholdGain,before:a.file,after:b.file});
    if(mode==='--all-frames'&&Math.round(time*60)%30===0)console.log('Compared '+Math.round(time*60)+'/120');
  }
  const report={mode:mode||'same-skeleton',identities,samples,interpretation:'Raster changes only; alpha-threshold changes are not automatically seam failures.',authority:'none',production_authorized:false};
  await fs.writeFile(path.join(output,'comparison.json'),JSON.stringify(report,null,2));
  const rows=samples.filter(r=>r.before).map(r=>`<section><h2>${r.time}s：变化 ${r.changed_pixels} 像素，最大通道差 ${r.max_channel_delta}</h2><div><figure><img src="${r.before}"><figcaption>原候选</figcaption></figure><figure><img src="${r.after}"><figcaption>边缘归属候选</figcaption></figure></div></section>`).join('');
  await fs.writeFile(path.join(output,'index.html'),`<!doctype html><meta charset="utf-8"><title>边缘候选同帧对照</title><style>body{font:17px/1.6 system-ui;max-width:1200px;margin:30px auto;background:#f4f6f8;color:#243448}div{display:flex}figure{width:50%;margin:5px}img{width:100%}</style><h1>边缘候选：官方 Runtime 同帧对照</h1><p>同骨架、动作和 Runtime。像素变化及 alpha 阈值跨越不直接判定为裂缝；候选未获得采用权。</p><a href="comparison.json">数值记录</a>${rows}`);
  console.log(JSON.stringify(mode==='--all-frames'?{frames:samples.length,max_delta:Math.max(...samples.map(s=>s.max_channel_delta)),alpha8_loss:Math.max(...samples.map(s=>s.alpha8_loss_pixels)),alpha8_gain:Math.max(...samples.map(s=>s.alpha8_gain_pixels))}:samples));
}finally{await browser.close();}
