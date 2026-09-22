// Exercise reversible plans only; never submit stage acceptance.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [base,jobId,output,dependencies,mode='partition']=process.argv.slice(2);
assert.ok(['partition','pose_attachment'].includes(mode));
const {chromium}=await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try {
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const open=async()=>{
    await page.goto(new URL('/motions.html#'+jobId,base).href);
    await page.reload();
    const card=page.locator('#'+jobId);
    await card.getByRole('button',{name:'检查可用范围与待处理项',exact:true}).click();
    const show=card.getByRole('button',{name:'查看变形区域与处理方案',exact:true});
    await show.waitFor({timeout:120000});await show.click();
    const load=card.getByRole('button',{name:'加载处理草稿',exact:true}).first();
    await load.waitFor({timeout:120000});await load.click();
    await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(b=>b.textContent==='保存处理草稿'&&!b.disabled&&!b.closest('fieldset').disabled),{},{timeout:120000});
    return card;
  };
  let card=await open();
  const before=await (await page.request.get(`${base}/api/motions/${jobId}/repair-draft`)).json();
  // Do not overwrite any existing active intervention.
  assert.ok(!before.history.some(r=>r.action!=='withdraw' && !r.notes.startsWith('UI regression draft;')), 'Use a candidate without existing intervention plans');
  await card.getByLabel('异常处理路线').first().selectOption(mode);
  await card.getByLabel('异常处理说明').first().fill('UI regression draft; withdrawn after reload verification');
  const save=async()=>{
    const result=page.waitForResponse(r=>r.url().endsWith('/repair-draft')&&r.request().method()==='POST',{timeout:120000});
    await card.getByRole('button',{name:'保存处理草稿',exact:true}).first().click();
    const response=await result;assert.ok(response.ok());return response.json();
  };
  const saved=await save();assert.equal(saved.revision,before.revision+1);
  card=await open();assert.equal(await card.getByLabel('异常处理路线').first().inputValue(),mode);
  assert.match(await card.getByLabel('异常处理说明').first().inputValue(),/UI regression/);
  let materialUrl=null;
  if(mode==='pose_attachment') {
    const link=card.getByRole('link',{name:'下载姿态素材任务包',exact:true}).first();
    await link.waitFor();materialUrl=await link.getAttribute('href');
    const pending=page.waitForEvent('download',{timeout:120000});await link.click();
    const download=await pending;await fs.mkdir(output,{recursive:true});
    await download.saveAs(path.join(output,'pose-material-request.zip'));
    assert.equal(await download.failure(),null);
  }
  await card.getByLabel('异常处理路线').first().selectOption('withdraw');
  const withdrawn=await save();assert.equal(withdrawn.history.at(-1).action,'withdraw');
  if(materialUrl)assert.equal((await page.request.get(new URL(materialUrl,base).href)).status(),400);
  assert.equal(withdrawn.repair_executed,false);assert.deepEqual(errors,[]);
  await fs.mkdir(output,{recursive:true});await card.screenshot({path:path.join(output,'draft.png')});
  await fs.writeFile(path.join(output,'check.json'),JSON.stringify({passed:true,jobId,artifact:saved.artifact_sha256,
    savedRevision:saved.revision,withdrawnRevision:withdrawn.revision,materialUrl,errors,scope:'draft_save_reload_export_withdraw_only'},null,2));
  console.log(JSON.stringify({passed:true,revision:withdrawn.revision}));
} finally {await browser.close();}
