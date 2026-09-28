import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome,id]=process.argv.slice(2);assert.match(id,/^motion-[a-f0-9]{32}$/);await fs.mkdir(output);
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(`http://127.0.0.1:8918/motion-editor.html#${id}`);
  await page.getByText('下载此候选 Spine 包',{exact:true}).waitFor({timeout:45000});
  await page.getByText('检查可用范围与待处理项',{exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#build-result h4'));
  const report=await page.locator('#build-result').innerText();
  const downloadPromise=page.waitForEvent('download');await page.getByText('下载此候选 Spine 包',{exact:true}).click();
  const download=await downloadPromise;await download.saveAs(path.join(output,'candidate.zip'));assert.equal(await download.failure(),null);
  await page.screenshot({path:path.join(output,'result.png'),fullPage:true});
  await page.goto(`http://127.0.0.1:8918/api/motions/${id}/view/player.html?time=0.5`);
  await page.waitForFunction(()=>window.characterPlayerReady,{},{timeout:45000});
  const state=await page.evaluate(()=>window.characterPlayerState);assert.ok(Math.abs(state.time-.5)<.001);
  await page.screenshot({path:path.join(output,'player.png')});assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({passed:true,job_id:id,errors,report,state},null,2));
}finally{await browser.close();}
