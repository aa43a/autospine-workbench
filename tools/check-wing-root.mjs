import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const [root,dependencies,chrome]=process.argv.slice(2);
const require=createRequire(path.resolve(dependencies,'package.json'));
const {chromium}=require('playwright-core');
const doc=JSON.parse(await fs.readFile(path.join(root,'roots.json'),'utf8'));
const browser=await chromium.launch({executablePath:chrome,headless:true});
try{
 const page=await browser.newPage({viewport:{width:1450,height:1200}}),errors=[];
 page.on('pageerror',e=>errors.push(String(e)));
 await page.goto(pathToFileURL(path.resolve(root,'review.html')).href);
 const groups=doc.rows.flatMap(r=>r.components),count=groups.flatMap(r=>r.roots).length;
 assert.equal(await page.locator('svg path').count(),count);
 assert.equal(await page.locator('section li').count(),groups.length);
 assert.ok(doc.rows.every(r=>r.selected_root===null&&!r.occlusion_verified&&!r.draw_order_reviewed));
 await page.screenshot({path:path.join(root,'review.png')});
 assert.deepEqual(errors,[]);
 await fs.writeFile(path.join(root,'browser.json'),JSON.stringify({components:groups.length,roots:count,errors},null,2));
}finally{await browser.close();}
