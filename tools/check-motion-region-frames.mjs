// Same-candidate, same-camera isolation: visibility diagnosis, not acceptance.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [url,output,dependencies]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,
  args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
 const page=await browser.newPage({viewport:{width:1400,height:1200}});
 await page.goto(url);await page.waitForFunction(()=>window.characterPlayerReady);
 await page.getByText('部件与遮挡对照',{exact:true}).click();
 await fs.mkdir(output,{recursive:true});
 const artifact=await page.evaluate(()=>window.characterPlayerControl.artifact),rows=[];
 for(const time of [0,.8,.9,1.2,1.866667]){
  for(const slot of ['full','layer-003','layer-004']){
   await page.selectOption('#inspect-a',slot==='full'?'':slot);
   await page.selectOption('#inspect-mode',slot==='full'?'full':'isolate');
   assert.equal(await page.evaluate(t=>window.characterPlayerControl.seek(t),time),true);
   const file=`${slot}-${time}.png`;
   await page.locator('canvas').screenshot({path:path.join(output,file)});
   let pixelProbe=null;
   if(time===.9&&slot!=='full'){
    const pixel=slot==='layer-003'?[216,489]:[325,477];
    pixelProbe=await page.evaluate(({pixel,time})=>{
     window.characterPlayerControl.seek(time);
     const canvas=document.querySelector('canvas'),rect=canvas.getBoundingClientRect(),gl=canvas.getContext('webgl');
     const x=Math.floor((pixel[0]+.5)/rect.width*canvas.width);
     const y=Math.floor((1-(pixel[1]+.5)/rect.height)*canvas.height);
     const rgba=new Uint8Array(4);gl.readPixels(x,y,1,1,gl.RGBA,gl.UNSIGNED_BYTE,rgba);
     return {screenshot_pixel:pixel,framebuffer_pixel:[x,y],rgba:Array.from(rgba)};
    },{pixel,time});
   }
   rows.push({time,slot,file,pixelProbe,state:await page.evaluate(()=>window.characterPlayerState)});
  }
 }
 await fs.writeFile(path.join(output,'report.json'),JSON.stringify({artifact,rows,authority:'none',selected:false},null,2));
 await fs.writeFile(path.join(output,'index.html'),'<!doctype html><meta charset="utf-8"><title>腿部同帧隔离</title><style>body{background:#172430;color:white;font:16px sans-serif}section{display:flex}figure{width:32%;margin:4px}img{width:100%;background:repeating-conic-gradient(#293849 0% 25%,#354558 0% 50%) 0/20px 20px}</style><h1>同帧、同相机完整角色与双腿</h1><p>只读隔离，不改变候选；不同区域的几何与外观分别判断。</p>'+[0,.8,.9,1.2,1.866667].map(t=>`<h2>${t} 秒</h2><section>${rows.filter(r=>r.time===t).map(r=>`<figure><figcaption>${r.slot}</figcaption><img src="${r.file}"></figure>`).join('')}</section>`).join(''));
 console.log(JSON.stringify({artifact,captures:rows.length}));
}finally{await browser.close();}
