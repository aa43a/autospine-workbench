import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome,run]=process.argv.slice(2);
await fs.mkdir(output,{recursive:true});
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(`http://127.0.0.1:8918/production.html?run=${run}`);
  await page.waitForSelector('#player:not([hidden])');
  await page.getByRole('button',{name:'记录 / 查看阶段验收'}).click();
  await page.getByLabel('阶段验收结论',{exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'保存阶段结论'}).isDisabled(),true);
  const href=await page.getByRole('link',{name:'下载 Spine 候选',exact:true}).getAttribute('href');
  const download=await page.request.get(new URL(href,page.url()).href);
  assert.equal(download.status(),200);
  const bytes=await download.body();assert.equal(bytes.subarray(0,2).toString(),'PK');
  await fs.writeFile(path.join(output,'candidate.zip'),bytes);
  await page.screenshot({path:path.join(output,'review.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({passed:true,run,download_bytes:bytes.length,stage_review_saved:false,errors},null,2));
  console.log(JSON.stringify({passed:true,download_bytes:bytes.length}));
}finally{await browser.close();}
