import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
const [file,deps]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try{
 const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(pathToFileURL(path.resolve(file)).href);
 await page.locator('#time').fill('0.9');await page.locator('#time').dispatchEvent('input');
 const first=await page.evaluate(()=>window.projectionState);assert.ok(Math.abs(first.time-.9)<.04);
 await page.locator('#variant').selectOption({index:1});
 const second=await page.evaluate(()=>window.projectionState);assert.notEqual(first.variant,second.variant);assert.equal(first.frame,second.frame);
 await page.getByRole('button',{name:'播放',exact:true}).click();
 await page.waitForFunction(t=>window.projectionState.time>t,second.time);
 await page.getByRole('button',{name:'暂停',exact:true}).click();
 await page.screenshot({path:file+'.png',fullPage:true});assert.deepEqual(errors,[]);
 console.log(JSON.stringify({passed:true,first,second}));
}finally{await browser.close();}
