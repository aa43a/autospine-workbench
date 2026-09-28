import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome]=process.argv.slice(2);await fs.mkdir(output,{recursive:true});
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}});
  const errors=[];page.on('pageerror',e=>errors.push(String(e)));page.on('response',response=>{if(response.status()>=400)errors.push(`${response.status()} ${response.url()}`);});
  await page.goto('http://127.0.0.1:8918/motion-editor.html');
  try{await page.waitForFunction(()=>document.querySelectorAll('#source option').length>1&&document.querySelectorAll('#project option').length>1,null,{timeout:120000});}
  catch(error){await fs.writeFile(path.join(output,'failure.json'),JSON.stringify({errors,text:await page.locator('body').innerText()},null,2));throw error;}
  await page.selectOption('#project','yaomeng');await page.selectOption('#source','motion-c8f9555203bc4130abeaf37e523a16cb');
  await page.waitForFunction(()=>window.motionEditorPreviewState?.status==='raw_preview',null,{timeout:60000});
  await page.selectOption('#motion-layer-list','layer-002');
  await page.fill('#layer-dx','6');await page.locator('#layer-dx').dispatchEvent('change');
  await page.waitForFunction(()=>window.motionEditorPreviewState?.layer_edits?.transforms[0]?.dx===6);
  const overlay=page.locator('#character-canvas').locator('..').locator('canvas[aria-hidden=true]');
  const style=await overlay.evaluate(el=>({background:getComputedStyle(el).backgroundColor,outline:getComputedStyle(el).outlineStyle,minHeight:getComputedStyle(el).minHeight}));
  assert.equal(style.background,'rgba(0, 0, 0, 0)');assert.equal(style.outline,'none');assert.equal(style.minHeight,'0px');
  await page.locator('#character-canvas').locator('..').screenshot({path:path.join(output,'visible-character.png')});
  const face=await page.locator('#motion-layer-list option').evaluateAll(options=>options.find(o=>o.textContent.includes('face'))?.value);
  assert.ok(face);await page.selectOption('#motion-layer-list',face);
  await page.locator('#character-canvas').scrollIntoViewIfNeeded();
  const point=await overlay.evaluate(el=>{
    const p=el.getContext('2d').getImageData(0,0,el.width,el.height).data;let x0=el.width,y0=el.height,x1=0,y1=0;
    for(let y=0;y<el.height;y++)for(let x=0;x<el.width;x++)if(p[(y*el.width+x)*4+3]){x0=Math.min(x0,x);x1=Math.max(x1,x);y0=Math.min(y0,y);y1=Math.max(y1,y);}
    const r=el.getBoundingClientRect(),s=Math.min(r.width/el.width,r.height/el.height);
    return {x:r.left+(r.width-el.width*s)/2+(x0+x1)/2*s,y:r.top+(r.height-el.height*s)/2+(y0+y1)/2*s,scale:s};
  });
  const before=await page.evaluate(()=>window.motionEditorPreviewState.layer_edits);
  await page.mouse.move(point.x,point.y);await page.mouse.down();
  const picked=await page.locator('#motion-layer-list').inputValue();
  await page.mouse.move(point.x+18,point.y+12,{steps:5});await page.mouse.up();
  const expected=before.transforms.find(t=>t.slot===picked)??{dx:0,dy:0};
  await page.waitForFunction(({picked,expected,scale})=>{const t=window.motionEditorPreviewState?.layer_edits?.transforms.find(t=>t.slot===picked);return t&&Math.abs(t.dx-expected.dx-18/scale)<.01&&Math.abs(t.dy-expected.dy+12/scale)<.01;},{picked,expected,scale:point.scale});
  await page.locator('#character-canvas').locator('..').screenshot({path:path.join(output,'dragged-character.png')});
  await page.click('#undo-edit');
  try{await page.waitForFunction(value=>JSON.stringify(window.motionEditorPreviewState.layer_edits)===JSON.stringify(value),before);}
  catch(error){await fs.writeFile(path.join(output,'undo-failure.json'),JSON.stringify({before,after:await page.evaluate(()=>window.motionEditorPreviewState),status:await page.locator('#status').innerText()},null,2));throw error;}
  await page.setViewportSize({width:390,height:844});
  await page.waitForFunction(()=>{const c=document.querySelector('#character-canvas'),o=c.parentElement.querySelector('canvas[aria-hidden=true]');return Math.abs(c.getBoundingClientRect().width-o.getBoundingClientRect().width)<.5;});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.locator('#character-canvas').locator('..').screenshot({path:path.join(output,'mobile-character.png')});
  await page.selectOption('#source','');
  const opaque=await overlay.evaluate(el=>{const values=el.getContext('2d').getImageData(0,0,el.width,el.height).data;let count=0;for(let i=3;i<values.length;i+=4)if(values[i])count++;return count;});
  assert.equal(opaque,0);
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({passed:true,style,mobileResize:true,picked,dragCssDelta:[18,12],undoRestored:true,overlayOpaqueAfterClear:opaque,errors},null,2));
}finally{await browser.close();}
