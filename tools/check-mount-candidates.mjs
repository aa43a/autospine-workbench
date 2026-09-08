import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const [root,dependencies,chrome]=process.argv.slice(2);
const require=createRequire(path.resolve(dependencies,'package.json'));
const {chromium}=require('playwright-core');
const browser=await chromium.launch({executablePath:chrome,headless:true});
try{
 const page=await browser.newPage({viewport:{width:1450,height:1000}}), errors=[],results=[];
 page.on('pageerror',e=>errors.push(String(e)));
 for(const name of ['alice','lingxian','crino']){
  const doc=JSON.parse(await fs.readFile(path.join(root,name,'candidates.json'),'utf8'));
  await page.goto(pathToFileURL(path.resolve(root,name,'review.html')).href);
  assert.equal(await page.locator('article').count(),doc.layers.length);
  const options=doc.layers.flatMap(r=>r.mount_options);
  assert.equal(await page.locator('svg path').count(),options.filter(o=>o.nearest_alpha_xy!==null).length);
  assert.ok(doc.layers.every(r=>r.selected_option===null));
  await page.screenshot({path:path.join(root,name,'review.png')});
  results.push({name,layers:doc.layers.length,options:options.length});
 }
 assert.deepEqual(errors,[]);
 await fs.writeFile(path.join(root,'browser.json'),JSON.stringify({results,errors},null,2));
}finally{await browser.close();}
