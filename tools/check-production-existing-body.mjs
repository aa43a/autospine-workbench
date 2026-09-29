// Read-only check of the actual existing-body entry; never saves acceptance.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome,job,registration]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:chrome,headless:true});
let debugPage,errors=[],writes=[];
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});debugPage=page;
 page.on('pageerror',e=>errors.push(String(e)));page.on('request',r=>{if(r.method()==='POST')writes.push(r.url());});
 await page.goto('http://127.0.0.1:8918/production.html');
 await page.getByText('从已有身体候选继续制作',{exact:true}).click({timeout:120000});
 await page.getByRole('button',{name:'读取已有身体候选'}).click();
 await page.getByRole('combobox',{name:'已有身体动作',exact:true}).selectOption(job);
 await page.waitForFunction(()=>Array.from(document.querySelectorAll('button')).some(b=>b.textContent==='接入制作链'&&!b.disabled),{},{timeout:180000});
 await page.getByRole('combobox',{name:'已有身体修复版本',exact:true}).selectOption(registration);
 const panel=page.locator('details').filter({has:page.getByText('从已有身体候选继续制作',{exact:true})});
 await panel.screenshot({path:path.join(output,'existing-body.png')});
 assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
 await fs.writeFile(path.join(output,'report.json'),JSON.stringify({passed:true,job,registration,scope:'real sources, entry selection only',writes,errors},null,2));
 console.log(JSON.stringify({passed:true,job}));
}catch(e){await fs.writeFile(path.join(output,'failure.json'),JSON.stringify({error:String(e),errors,text:await debugPage?.locator('body').innerText()},null,2));throw e;}finally{await browser.close();}
