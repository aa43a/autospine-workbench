import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [base,jobId,output,dependencies]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,
 args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
 const page=await browser.newPage({viewport:{width:1400,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(new URL('/motions.html#'+jobId,base).href);const card=page.locator('#'+jobId);
 await card.getByRole('button',{name:'检查可用范围与待处理项',exact:true}).click();
 await card.getByRole('button',{name:'展开完整遮挡失败采样',exact:true}).click();
 const summary=card.locator('summary').filter({hasText:/^layer-004 ↔ layer-006/}).last();
 await summary.waitFor();const details=summary.locator('..');
 await summary.click();
 await details.getByRole('button',{name:'同页隔离冲突部件',exact:true}).click();
 await page.waitForFunction(id=>document.getElementById(id)?.querySelector('iframe')?.contentWindow?.characterInspectionState?.isolated,jobId,{timeout:120000});
 const actual=await card.locator('iframe').evaluate(frame=>({inspection:frame.contentWindow.characterInspectionState,
   time:frame.contentWindow.characterPlayerState.time,identity:frame.contentWindow.characterPlayerControl.artifact}));
 assert.deepEqual(actual.inspection.regions,['layer-004','layer-006']);assert.equal(actual.time,0);
 await fs.mkdir(output,{recursive:true});await card.locator('iframe').screenshot({path:path.join(output,'isolated.png')});
 await card.getByRole('button',{name:'显示完整角色',exact:true}).click();
 assert.equal(await card.locator('iframe').evaluate(frame=>frame.contentWindow.characterInspectionState.isolated),false);
 assert.deepEqual(errors,[]);
 await fs.writeFile(path.join(output,'check.json'),JSON.stringify({passed:true,actual,errors},null,2));
 console.log(JSON.stringify({passed:true,actual}));
} finally {await browser.close();}
