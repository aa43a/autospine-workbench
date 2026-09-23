import fs from 'node:fs';
import {createRequire} from 'node:module';
const require=createRequire(process.argv[2]+'/package.json');
const {chromium}=require('playwright-core');
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try {
  const page=await browser.newPage();await page.setContent('<main></main>');
  await page.addScriptTag({content:fs.readFileSync('web/modules/motion-material-return.js','utf8').replace('export function','function')});
  await page.evaluate(()=>{
    window.showReturn=materialReturn(document.querySelector('main'),{job_id:'job'});showReturn(2);
    window.fetch=async(url,options)=>{window.submitted={url,body:JSON.parse(options.body)};return {ok:true,json:async()=>({unchanged_source:false})};};
  });
  await page.getByLabel('素材任务身份文件').setInputFiles({name:'request.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({job_id:'other',draft_revision:2}))});
  await page.getByLabel('回交姿态图片').setInputFiles({name:'pose.png',mimeType:'image/png',buffer:Buffer.from('diagnostic mocked payload')});
  await page.getByRole('button',{name:'保存回交素材',exact:true}).click();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('不属于'));
  if(await page.evaluate(()=>Boolean(window.submitted)))throw Error('cross-job upload submitted');
  await page.getByLabel('素材任务身份文件').setInputFiles({name:'request.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({job_id:'job',draft_revision:2}))});
  await page.getByRole('button',{name:'保存回交素材',exact:true}).click();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('已保存独立'));
  const submission=await page.evaluate(()=>window.submitted);
  if(submission.url!='/api/motions/job/material-return'||!submission.body.png_base64)throw Error('bad upload');
  await page.evaluate(()=>showReturn(null));if(await page.locator('fieldset').isVisible())throw Error('stale form visible');
  console.log(JSON.stringify({passed:true,scope:'isolated_UI_mock_transport; backend_validates_PNG_separately'}));
}finally{await browser.close();}
