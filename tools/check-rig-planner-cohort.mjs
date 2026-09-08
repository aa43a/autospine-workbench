import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const [root,dependencies,chrome]=process.argv.slice(2);
const require=createRequire(path.resolve(dependencies,'package.json'));
const {chromium}=require('playwright-core');
const doc=JSON.parse(await fs.readFile(path.join(root,'cohort.json'),'utf8'));
const browser=await chromium.launch({executablePath:chrome,headless:true});
try {
 const page=await browser.newPage({viewport:{width:1450,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(String(e)));
 await page.goto(pathToFileURL(path.resolve(root,'summary.html')).href);
 assert.equal(await page.locator('table tr').count(),doc.characters.length+1);
 await page.screenshot({path:path.join(root,'summary.png')});
 for(const character of doc.characters){
  await page.getByRole('link',{name:character.label,exact:true}).click();
  await page.waitForURL('**/review.html');
  assert.equal(await page.locator('article').count(),character.total_layers);
  await page.screenshot({path:path.join(root,character.label,'review.png')});
  await page.goto(pathToFileURL(path.resolve(root,'summary.html')).href);
 }
 assert.deepEqual(errors,[]);
 await fs.writeFile(path.join(root,'browser.json'),JSON.stringify({characters:doc.characters.length,
  cards:doc.total_layers,errors},null,2));
}finally{await browser.close();}
