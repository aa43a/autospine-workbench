import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(pathToFileURL(path.resolve(process.argv[2])).href);
  const slider=page.getByRole('slider',{name:'动画时间轴'});
  const maximum=Number(await slider.getAttribute('max'));assert.ok(maximum>0);
  for(const index of [0,Math.floor(maximum/2),maximum]){
    await slider.fill(String(index));await slider.dispatchEvent('input');
    await page.waitForFunction(()=>{const img=document.querySelector('#frame');return img.complete&&img.naturalWidth>0;});
    assert.ok((await page.locator('#clock').textContent()).includes(`${index+1}/${maximum+1}`));
  }
  await slider.fill('0');await slider.dispatchEvent('input');
  await page.getByRole('button',{name:'播放',exact:true}).click();
  await page.waitForFunction(()=>Number(document.querySelector('#time').value)>0);
  await page.getByRole('button',{name:'暂停',exact:true}).click();
  assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,frames:maximum+1}));
}finally{await browser.close();}
