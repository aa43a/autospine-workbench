import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const [root,dependencies,chrome]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.join(dependencies,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true});
try{
 const page=await browser.newPage({viewport:{width:1500,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.goto(pathToFileURL(path.resolve(root,'review.html')).href);await page.waitForFunction(()=>window.projectionReady||window.projectionFailure);
 assert.equal(await page.evaluate(()=>window.projectionFailure),undefined);
 const base=JSON.parse(await fs.readFile(path.join(root,'draft.json'),'utf8')),groups=JSON.parse(await fs.readFile(path.join(root,'groups.json'),'utf8'));
 assert.equal(await page.locator('[data-group]').count(),4);
 for(let i=0;i<4;i++)assert.equal(await page.locator(`[data-group="${i}"]`).inputValue(),'uncertain');
 await page.locator('#reference').uncheck();
 const span=groups.groups[0].spans.find(r=>r[2]-r[1]>10),point=[span[1]+5,span[0]];
 const alpha=()=>page.evaluate(([x,y])=>document.querySelector('#preview').getContext('2d').getImageData(x,y,1,1).data[3],point);
 const original=await alpha();assert.ok(original>0);
 await page.locator('[data-group="0"]').selectOption('remove');assert.equal(await alpha(),0);
 await page.locator('#undo').click();assert.equal(await alpha(),original);
 for(let i=0;i<4;i++)await page.locator(`[data-group="${i}"]`).selectOption('remove');
 await page.locator('#mode').selectOption('keep');const b=await page.locator('#edit').boundingBox();
 await page.mouse.click(b.x+(point[0]+.1)*b.width/groups.canvas[0],b.y+(point[1]+.1)*b.height/groups.canvas[1]);assert.equal(await alpha(),original);
 async function save(){const wait=page.waitForEvent('download');await page.locator('#save').click();return JSON.parse(await fs.readFile(await (await wait).path(),'utf8'));}
 const draft=await save();assert.ok(draft.choices.every(r=>r.action==='remove'));assert.equal(draft.local_strokes.length,1);
 const wrong=structuredClone(draft);wrong.source_split_draft_sha256='0'.repeat(64);
 await page.locator('#load').setInputFiles({name:'bad.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(wrong))});await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('恢复失败'));assert.deepEqual(await save(),draft);
 await page.locator('#reset').click();assert.deepEqual(await save(),base);
 await page.locator('#load').setInputFiles({name:'valid.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(draft))});await page.waitForFunction(()=>document.querySelector('[data-group="0"]').value==='remove');assert.deepEqual(await save(),draft);
 await page.locator('#reset').click();await page.locator('#reference').check();await page.locator('#mode').selectOption('inspect');
 await page.screenshot({path:path.join(root,'browser-setup.png'),fullPage:true});assert.deepEqual(errors,[]);
 await fs.writeFile(path.join(root,'browser-check.json'),JSON.stringify({passed:true,groups:4,group_remove:true,local_keep_override:true,undo:true,restore_guard:true,delivered_actions:'uncertain',delivered_local_strokes:0,authority:'none',production_authorized:false},null,2));
 console.log('projection group editor passed');
}finally{await browser.close();}
