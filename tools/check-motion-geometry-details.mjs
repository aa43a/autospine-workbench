import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [url, output, dependencies] = process.argv.slice(2);
const {chromium} = await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
const browser = await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try {
  const page = await browser.newPage({viewport:{width:1100,height:1000}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto(url);
  await page.getByRole('button',{name:'查看变形区域与处理方案'}).click();
  await page.waitForFunction(()=>document.querySelector('canvas')?.height>150);
  const report=await (await page.request.get(new URL('geometry-details.json',url).href)).json();
  const row=report.rows[0];
  assert.equal(await page.locator('select option').count(),row.details.length);
  await page.getByRole('link',{name:'定位到此动作时刻'}).click();
  assert.equal(await page.evaluate(()=>window.lastSeek),row.details[0].time);
  await page.locator('select').selectOption('1');
  await page.getByRole('link',{name:'定位到此动作时刻'}).click();
  assert.equal(await page.evaluate(()=>window.lastSeek),row.details[1].time);
  const pixels=await page.locator('canvas').evaluate(canvas=>{
    const data=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
    let opaque=0,yellow=0;
    for(let i=0;i<data.length;i+=4){if(data[i+3]>0)opaque++;if(data[i]>240&&data[i+1]>180&&data[i+2]<30)yellow++;}
    return {opaque,yellow,width:canvas.width,height:canvas.height};
  });
  assert.ok(pixels.opaque>1000 && pixels.yellow>0);
  await fs.mkdir(output,{recursive:true});
  await page.screenshot({path:path.join(output,'inspector.png'),fullPage:true});
  await page.route('**/geometry-details.json',route=>route.fulfill({json:{...report,artifact_sha256:'different'}}));
  await page.getByRole('button',{name:'查看变形区域与处理方案'}).click();
  await page.getByText('无法定位：候选版本已变化，请刷新任务').waitFor();
  assert.equal(await page.locator('canvas').count(),0);
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'check.json'),JSON.stringify({passed:true,candidate:report.artifact_sha256,pixels,
    checks:['actual_texture_and_uv_overlay','selection','seek_callback','identity_rejection'],errors},null,2));
  console.log(JSON.stringify({passed:true,pixels}));
} finally {await browser.close();}
