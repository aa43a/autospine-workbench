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
 const page=await browser.newPage({viewport:{width:1450,height:1100}}),errors=[],results=[];
 page.on('pageerror',e=>errors.push(String(e)));
 for(const name of ['alice','lingxian','crino']){
  const doc=JSON.parse(await fs.readFile(path.join(root,name,'search.json'),'utf8'));
  await page.goto(pathToFileURL(path.resolve(root,name,'review.html')).href);
  const count=doc.rows.flatMap(r=>r.candidates).length;
  assert.equal(await page.locator('article').count(),count);
  assert.equal(await page.locator('svg').count(),count);
  assert.equal(await page.locator('body > ul > li').count(),doc.rows.filter(r=>!r.candidates.length).length);
  assert.ok(doc.rows.every(r=>r.selected_candidate===null));
  await page.screenshot({path:path.join(root,name,'review.png')});
  results.push({name,candidates:count});
 }
 assert.deepEqual(errors,[]);
 await fs.writeFile(path.join(root,'browser.json'),JSON.stringify({results,errors},null,2));
}finally{await browser.close();}
