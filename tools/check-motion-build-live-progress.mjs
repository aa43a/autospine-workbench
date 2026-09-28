// Read-only verification of a real running build; never submits or cancels jobs.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome,id]=process.argv.slice(2);
assert.match(id,/^motion-[a-f0-9]{32}$/);await fs.mkdir(output,{recursive:true});
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true});
try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(`http://127.0.0.1:8918/motion-editor.html#${id}`);
  await page.waitForFunction(()=>document.querySelector('#build-status').textContent.includes('已用时'));
  const first=await page.locator('#build-status').innerText();
  assert.match(first,/构建中/);assert.equal(await page.locator('#build').isDisabled(),true);
  await page.waitForFunction(old=>document.querySelector('#build-status').innerText!==old,first,{timeout:15000});
  const second=await page.locator('#build-status').innerText();
  await page.locator('#build-status').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(output,'live-progress.png')});
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({passed:true,id,first,second,errors,evidence:'real running build; no mocked requests'},null,2));
}finally{await browser.close();}
