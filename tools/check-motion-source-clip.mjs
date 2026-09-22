import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [base,jobId,output,dependencies]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,
  args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
  const page=await browser.newPage({viewport:{width:1400,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(new URL('/motions.html#'+jobId,base).href);
  const card=page.locator('#'+jobId);
  await card.getByRole('button',{name:'在当前页播放与定位',exact:true}).click();
  await page.waitForFunction(id=>document.getElementById(id)?.querySelector('iframe')?.contentWindow?.characterPlayerReady,jobId,{timeout:120000});
  await card.getByRole('button',{name:'同步源骨架对照',exact:true}).click();
  await card.getByText('共用时间轴；骨架显示最近源采样，观察视角不修改角色动画。',{exact:true}).waitFor();
  const report=await (await page.request.get(new URL(`/api/motions/${jobId}/view/source-comparison.json`,base).href)).json();
  assert.ok(report.source_start>0,'Use a real nonzero clip');
  const slider=card.getByRole('slider',{name:'源与角色共用时间轴',exact:true});
  assert.equal(Number(await slider.getAttribute('min')),report.source_start);
  const observed=[];
  for(const relative of [0,.5,report.duration]) {
    await slider.evaluate((el,time)=>{el.value=time;el.dispatchEvent(new Event('input'));},report.source_start+relative);
    const actual=await card.locator('iframe').evaluate(frame=>frame.contentWindow.characterPlayerState.time);
    assert.ok(Math.abs(actual-relative)<.002,`${actual} != ${relative}`);observed.push({relative,actual});
  }
  await fs.mkdir(output,{recursive:true});
  await card.locator('.motion-inline-player').screenshot({path:path.join(output,'source-clip.png')});
  await card.getByRole('button',{name:'关闭播放器',exact:true}).click();
  assert.equal(await card.locator('iframe').count(),0);assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'source-clip.json'),JSON.stringify({passed:true,jobId,
    candidate:report.artifact_sha256,sourceStart:report.source_start,sourceEnd:report.source_end,observed,errors},null,2));
  console.log(JSON.stringify({passed:true,observed}));
} finally {await browser.close();}
