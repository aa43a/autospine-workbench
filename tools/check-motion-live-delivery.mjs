// Read-only verification of the completed candidate through the ordinary UI.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [base,jobId,output,dependencies]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,
  args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
  const page=await browser.newPage({viewport:{width:1400,height:1000},acceptDownloads:true});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const job=await (await page.request.get(new URL('/api/motions/'+jobId,base).href)).json();
  assert.equal(job.status,'succeeded');
  await page.goto(new URL('/motions.html#'+jobId,base).href);
  const card=page.locator('#'+jobId);
  await card.getByRole('button',{name:'在当前页播放与定位',exact:true}).click();
  await page.waitForFunction(id=>document.getElementById(id)?.querySelector('iframe')?.contentWindow?.characterPlayerReady,jobId,{timeout:120000});
  const identity=await card.locator('iframe').evaluate(frame=>frame.contentWindow.characterPlayerControl.artifact);
  assert.equal(identity,job.result.artifact_sha256);
  await card.getByRole('button',{name:'同步源骨架对照',exact:true}).click();
  await card.getByText('共用时间轴；骨架显示最近源采样，观察视角不修改角色动画。',{exact:true}).waitFor();
  const slider=card.getByRole('slider',{name:'源与角色共用时间轴',exact:true});
  const start=Number(await slider.getAttribute('min')),end=Number(await slider.getAttribute('max'));
  const samples=[];await fs.mkdir(output,{recursive:true});
  for(const factor of [0,.5,1]) {
    const relative=(end-start)*factor;
    await slider.evaluate((el,time)=>{el.value=time;el.dispatchEvent(new Event('input'));},start+relative);
    const actual=await card.locator('iframe').evaluate(frame=>frame.contentWindow.characterPlayerState.time);
    assert.ok(Math.abs(actual-relative)<.002);samples.push({relative,actual});
    await card.locator('iframe').screenshot({path:path.join(output,`frame-${factor}.png`)});
  }
  const downloaded=page.waitForEvent('download');
  await card.getByRole('link',{name:'下载诊断候选 ZIP',exact:true}).click();
  await (await downloaded).saveAs(path.join(output,'candidate.zip'));
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'browser-delivery.json'),JSON.stringify({passed:true,jobId,
    artifact:identity,samples,errors,scope:'live_ui_playback_seek_and_download_not_visual_acceptance'},null,2));
  console.log(JSON.stringify({passed:true,jobId,artifact:identity,samples}));
} finally {await browser.close();}
