import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [base, jobId, output, dependencies] = process.argv.slice(2);
const {chromium} = await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
const browser = await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
  const page=await browser.newPage({viewport:{width:1400,height:1000}});
  const errors=[]; page.on('pageerror',error=>errors.push(error.message));
  await page.goto(new URL('/motions.html#'+jobId,base).href);
  const card=page.locator('#'+jobId);
  await card.getByRole('button',{name:'检查可用范围与待处理项',exact:true}).click();
  await card.getByRole('button',{name:'查看变形区域与处理方案',exact:true}).click();
  await card.getByRole('link',{name:'定位时间并高亮动作区域',exact:true}).first().waitFor();
  assert.equal(await card.locator('iframe').count(),0,'Player must be lazy');
  await card.getByRole('link',{name:'定位时间并高亮动作区域',exact:true}).first().click();
  await page.waitForFunction(id=>document.getElementById(id)?.querySelector('iframe')?.contentWindow?.characterTriangleInspection?.points?.length===3,jobId,{timeout:120000});
  const report=await (await page.request.get(new URL(`/api/motions/${jobId}/view/geometry-details.json`,base).href)).json();
  const actual=await card.locator('iframe').evaluate(frame=>({
    identity:frame.contentWindow.characterPlayerControl.artifact,
    time:frame.contentWindow.characterPlayerState.time,
    triangle:frame.contentWindow.characterTriangleInspection}));
  assert.equal(actual.identity,report.artifact_sha256);
  assert.equal(actual.time,report.rows[0].details[0].time);
  assert.equal(actual.triangle.index,report.rows[0].details[0].triangle);
  assert.equal(actual.triangle.slot,report.rows[0].slot);
  assert.equal(page.context().pages().length,1,'Inspection must stay on this page');
  await card.getByRole('button',{name:'同步源骨架对照',exact:true}).click();
  await card.getByText('共用时间轴；骨架显示最近源采样，观察视角不修改角色动画。',{exact:true}).waitFor();
  const timeline=card.getByRole('slider',{name:'源与角色共用时间轴',exact:true});
  await timeline.evaluate(el=>{el.value='0.5';el.dispatchEvent(new Event('input'));});
  assert.equal(await card.locator('iframe').evaluate(frame=>frame.contentWindow.characterPlayerState.time),.5);
  assert.equal(await card.locator('iframe').evaluate(frame=>frame.contentWindow.document.getElementById('time').disabled),true);
  await fs.mkdir(output,{recursive:true});
  await card.locator('iframe').screenshot({path:path.join(output,'inline-player.png')});
  // An already-loaded wrong candidate must receive neither seek nor highlight.
  await card.locator('iframe').evaluate(frame=>{
    frame.contentWindow.characterPlayerControl={artifact:'wrong',seek:()=>{throw Error('wrong candidate was controlled');}};
  });
  await card.getByRole('link',{name:'定位时间并高亮动作区域',exact:true}).first().click();
  await card.getByText('定位未完成：候选身份不一致，请刷新任务',{exact:true}).waitFor();
  assert.equal(await card.locator('iframe').evaluate(frame=>frame.contentWindow.document.getElementById('time').disabled),false);
  await card.getByRole('button',{name:'关闭播放器',exact:true}).click();
  assert.equal(await card.locator('iframe').count(),0);
  assert.deepEqual(errors,[]);
  await fs.mkdir(output,{recursive:true});
  await fs.writeFile(path.join(output,'check.json'),JSON.stringify({passed:true,jobId,actual,
    checks:['live_motion_center','lazy_load','queued_seek_and_highlight','source_timeline_sync','no_navigation','identity_guard','close_disposes_player'],errors},null,2));
  console.log(JSON.stringify({passed:true,jobId,actual}));
} finally {await browser.close();}
