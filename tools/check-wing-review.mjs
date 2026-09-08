import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const [root,dependencies,chrome,html="review.html"]=process.argv.slice(2);
const require=createRequire(path.resolve(dependencies,'package.json'));
const {chromium}=require('playwright-core');
const base=JSON.parse(await fs.readFile(path.join(root,'draft.json'),'utf8'));
const browser=await chromium.launch({executablePath:chrome,headless:true});
try{
 const page=await browser.newPage({viewport:{width:1450,height:1100}}),errors=[];
 page.on('pageerror',e=>errors.push(String(e)));
 await page.goto(pathToFileURL(path.resolve(root,html)).href);
 assert.equal(await page.locator('select[data-record]').count(),base.records.length);
 assert.equal(await page.locator('select[data-record]:enabled').count(),4);
 const first=page.locator('select[data-record="0"]');
 assert.equal(await first.inputValue(),'');
 await first.selectOption('0');
 await page.locator('#chest-angle').evaluate(e=>{e.value='10';e.dispatchEvent(new Event('input'));});
 await page.locator('#flap-angle').evaluate(e=>{e.value='12';e.dispatchEvent(new Event('input'));});
 const difference=await page.evaluate(()=>{
  const state=JSON.parse(document.getElementById('state').textContent),r=state.roots.rows[0].components[0].roots[0].source_xy;
  const p=new DOMPoint(r[0],r[1]);
  const a=p.matrixTransform(document.querySelector('[data-wing="0"]').getCTM());
  const b=p.matrixTransform(document.getElementById('stage').getCTM());
  return Math.hypot(a.x-b.x,a.y-b.y);
 });
 assert.ok(difference<1e-6);
 await first.selectOption('1');await page.locator('#undo').click();assert.equal(await first.inputValue(),'0');
 await page.locator('#front').uncheck();
 assert.equal(await page.locator('#stage').evaluate(e=>e.firstElementChild.id),'wings');
 const waiting=page.waitForEvent('download');await page.locator('#save').click();
 const download=await waiting,saved=JSON.parse(await fs.readFile(await download.path(),'utf8'));
 const expected=structuredClone(base);expected.records[0].root_index=0;assert.deepEqual(saved,expected);
 await page.screenshot({path:path.join(root,'motion-test.png')});
 await page.locator('#load').setInputFiles(path.resolve(root,'draft.json'));
 await page.waitForFunction(()=>document.getElementById('load').value==='');
 assert.equal(await first.inputValue(),'');
 const bad=structuredClone(base);bad.source_roots_sha256='0'.repeat(64);
 await page.locator('#load').setInputFiles({name:'wrong-source.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(bad))});
 await page.waitForFunction(()=>document.getElementById('status').textContent.includes('来源'));
 assert.equal(await first.inputValue(),'');
 await page.locator('#reset-pose').click();await page.locator('#front').check();
 await page.screenshot({path:path.join(root,'setup.png')});
 assert.deepEqual(errors,[]);
 await fs.writeFile(path.join(root,'browser.json'),JSON.stringify({records:base.records.length,selectable_components:4,
  pivot_error:difference,full_draft_download:true,undo:true,restore:true,wrong_source_rejected:true,errors},null,2));
}finally{await browser.close();}
