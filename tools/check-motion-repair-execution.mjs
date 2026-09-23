// Submit a diagnostic local-repair candidate. No stage acceptance is written.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [base,parent,output,dependencies]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try {
  const page=await browser.newPage({viewport:{width:1600,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(`${base}/motions.html#${parent}`);
  const card=page.locator('#'+parent);
  await card.getByRole('button',{name:'检查可用范围与待处理项',exact:true}).click();
  const show=card.getByRole('button',{name:'查看变形区域与处理方案',exact:true});
  await show.waitFor({timeout:120000});await show.click();
  const load=card.getByRole('button',{name:'加载处理草稿',exact:true}).first();
  await load.waitFor({timeout:120000});
  const loading=page.waitForResponse(r=>r.url().endsWith('/repair-draft'),{timeout:120000});await load.click();
  const state=await (await loading).json();
  assert.ok(state.history.every(r=>r.notes.startsWith('UI regression draft;')||r.action==='withdraw'));
  await card.getByLabel('异常处理路线').first().selectOption('local_repair');
  await card.getByLabel('异常处理说明').first().fill('UI regression draft; real local repair execution verification');
  const saving=page.waitForResponse(r=>r.url().endsWith('/repair-draft')&&r.request().method()==='POST',{timeout:120000});
  await card.getByRole('button',{name:'保存处理草稿',exact:true}).first().click();
  const saved=await (await saving).json();assert.equal(saved.revision,state.revision+1);
  const submitting=page.waitForResponse(r=>r.url().endsWith('/repair-execute'),{timeout:120000});
  await card.getByRole('button',{name:'构建局部修正候选',exact:true}).first().click();
  const response=await submitting;assert.ok(response.ok());const job=await response.json();
  assert.equal(job.repair_parent_job_id,parent);assert.deepEqual(errors,[]);
  await card.getByRole('link',{name:'查看修正任务进度与结果'}).waitFor();
  await fs.mkdir(output,{recursive:true});
  await fs.writeFile(path.join(output,'submission.json'),JSON.stringify({parent,job,draftRevision:saved.revision,errors},null,2));
  await card.screenshot({path:path.join(output,'submission.png')});
  console.log(JSON.stringify(job));
} finally {await browser.close();}
