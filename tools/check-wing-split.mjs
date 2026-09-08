import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const [root,dependencies,chrome,html='review.html']=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.join(dependencies,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true});
try{
 const page=await browser.newPage({viewport:{width:1550,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.goto(pathToFileURL(path.resolve(root,html)).href);await page.waitForFunction(()=>window.splitReady||window.splitFailure);
 assert.equal(await page.evaluate(()=>window.splitFailure),undefined);
 const base=JSON.parse(await fs.readFile(path.join(root,'draft.json'),'utf8'));assert.equal(base.strokes.length,0);
 await page.locator('#reference').uncheck();await page.locator('#hints').uncheck();
 const spot=await page.evaluate(()=>{
   const c=document.querySelector('#edit'),data=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
   for(let y=10;y<c.height*.4;y++)for(let x=10;x<c.width*.4;x++)if(data[(y*c.width+x)*4+3]>200)return [x,y];
   throw Error('no_visible_paint_spot');
 });
 const value=()=>page.evaluate(([x,y])=>document.querySelector('#preview').getContext('2d').getImageData(x,y,1,1).data[3],spot);
 const original=await value();assert.ok(original>200);
 async function click(){const b=await page.locator('#edit').boundingBox();await page.mouse.click(b.x+(spot[0]+.1)*b.width/base.canvas[0],b.y+(spot[1]+.1)*b.height/base.canvas[1]);}
 const bounds=await page.locator('#edit').boundingBox();
 const start=[bounds.x+(spot[0]+.1)*bounds.width/base.canvas[0],bounds.y+(spot[1]+.1)*bounds.height/base.canvas[1]];
 await page.mouse.move(...start);await page.mouse.down();await page.mouse.move(start[0]+10,start[1]+5,{steps:5});await page.mouse.up();assert.equal(await value(),0);
 await page.locator('#undo').click();assert.equal(await value(),original);
 await page.locator('#redo').click();assert.equal(await value(),0);
 await page.locator('#mode').selectOption('keep');await click();assert.equal(await value(),original);
 await page.locator('#mode').selectOption('erase');await click();assert.equal(await value(),original);
 await page.locator('#undo').click();
 async function save(){const waiting=page.waitForEvent('download');await page.locator('#save').click();const download=await waiting;return JSON.parse(await fs.readFile(await download.path(),'utf8'));}
 const saved=await save();assert.equal(saved.strokes.length,2);assert.ok(saved.strokes[0].points.length>1);assert.equal(saved.strokes[0].mode,'remove');assert.equal(saved.strokes[1].mode,'keep');
 const invalid=structuredClone(saved);invalid.source_preview_sha256='0'.repeat(64);
 await page.locator('#load').setInputFiles({name:'wrong.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(invalid))});
 await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('恢复失败'));assert.deepEqual(await save(),saved);
 await page.locator('#clear').click();assert.equal((await save()).strokes.length,0);
 await page.locator('#undo').click();assert.deepEqual(await save(),saved);
 await page.locator('#load').setInputFiles({name:'valid.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(saved))});
 await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('2 笔'));assert.deepEqual(await save(),saved);
 await page.locator('#zoom').evaluate(e=>{e.value='75';e.dispatchEvent(new Event('input'));});
 assert.ok(Math.abs((await page.locator('#edit').boundingBox()).width-base.canvas[0]*.75)<1);
 // Discard browser test choices: the delivered draft remains completely unmarked.
 await page.locator('#load').setInputFiles({name:'initial.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(base))});
 await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('0 笔'));
 await page.locator('#zoom').evaluate(e=>{e.value='50';e.dispatchEvent(new Event('input'));});
 await page.locator('#reference').check();await page.locator('#hints').check();
 await page.locator('#mode').selectOption('remove');
 await page.screenshot({path:path.join(root,'browser-setup.png'),fullPage:true});assert.deepEqual(errors,[]);
 await fs.writeFile(path.join(root,'browser-check.json'),JSON.stringify({passed:true,paint_remove_keep_erase:true,undo_redo:true,reset_undo:true,restore_source_guard:true,zoom:true,delivered_strokes:0,authority:'none',production_authorized:false},null,2));
 console.log('wing split editor checks passed');
}finally{await browser.close();}
