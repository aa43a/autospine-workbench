// Creates one independent diagnostic candidate through the actual editor UI.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome]=process.argv.slice(2);await fs.mkdir(output);
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto('http://127.0.0.1:8918/motion-editor.html');
  await page.waitForFunction(()=>document.querySelectorAll('#source option').length>1&&document.querySelectorAll('#project option').length>1);
  await page.selectOption('#project','alice');await page.selectOption('#source','motion-2671c6fdbc10444592420e6f8f4ad838');
  await page.waitForFunction(()=>!document.getElementById('time').disabled&&document.getElementById('character').getAttribute('src'));
  const response=page.waitForResponse(r=>r.url().endsWith('/adapt')&&r.request().method()==='POST');
  await page.click('#build');const submitted=await response;
  assert.equal(submitted.status(),202);const job=await submitted.json();
  await fs.writeFile(path.join(output,'submitted.json'),JSON.stringify(job,null,2));
  await page.waitForFunction(id=>location.hash===`#${id}`,job.job_id);
  await page.reload();
  await page.waitForFunction(()=>document.getElementById('build-status').textContent!=='尚未提交构建。');
  await page.screenshot({path:path.join(output,'running.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({submitted:true,reopened:true,job_id:job.job_id,errors},null,2));
}finally{await browser.close();}
