import {pathToFileURL} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
try{
  const page=await browser.newPage();const errors=[];
  page.on('pageerror',error=>errors.push(String(error)));
  await page.goto(pathToFileURL(path.resolve(process.argv[2])).href);
  await page.locator('#peak').click();
  await page.waitForFunction(()=>['before','after'].every(n=>document.querySelector('#'+n).naturalWidth>0));
  assert.match(await page.locator('#stats').textContent(),/改变像素 1066/);
  assert.match(await page.locator('#label').textContent(),/0\.891667/);
  await page.locator('#time').evaluate(el=>{el.value=0;el.dispatchEvent(new Event('input'));});
  assert.equal(await page.locator('#label').textContent(),'0.000000 s');
  await page.locator('#play').click();
  await page.waitForFunction(()=>+document.querySelector('#time').value>0);
  await page.locator('#play').click();
  assert.equal(await page.locator('#play').textContent(),'播放');
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,checks:['peak-frame','images-loaded','scrub','play-pause','no-page-errors']}));
}finally{await browser.close();}
