import {pathToFileURL} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
try{
  const page=await browser.newPage();const errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(pathToFileURL(path.resolve(process.argv[2])).href);
  await page.waitForFunction(()=>['full','zoom'].every(id=>document.querySelector('#'+id).naturalWidth>0));
  assert.match(await page.locator('#status').textContent(),/33 像素/);
  assert.equal(await page.locator('#legend span').count(),3);
  await page.locator('#seek').evaluate(el=>{el.value=1;el.dispatchEvent(new Event('input'));});
  assert.match(await page.locator('#status').textContent(),/1 像素/);
  assert.match(await page.locator('#frame option:checked').textContent(),/0\.450000/);
  await page.waitForFunction(()=>document.querySelector('#zoom').complete&&document.querySelector('#zoom').naturalWidth>0);
  await page.locator('#frame').selectOption('0');
  assert.equal(await page.locator('#seek').inputValue(),'0');
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,checks:['heatmap-images','legend','scrub','selection','no-page-errors']}));
}finally{await browser.close();}
