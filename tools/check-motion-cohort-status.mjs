import fs from 'node:fs';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const {chromium}=createRequire(process.argv[2]+'/package.json')('playwright-core');
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try{
  const page=await browser.newPage();await page.setContent('<main></main>');
  await page.addScriptTag({content:fs.readFileSync('web/modules/motion-cohort-status.js','utf8').replace('export function','function')});
  await page.evaluate(()=>{
    window.calls=[];window.stale=false;
    window.fetch=async(url,options)=>{
      calls.push({url,method:options.method||'GET'});
      const id=url.split('/')[3];const review=url.endsWith('/stage-review');
      return {ok:true,json:async()=>id==='source'?{status:'succeeded',source_sha256:'sourcehash'}:
        review?{artifact_sha256:stale&&id==='b'?'changed':id,readiness:{artifact_sha256:id,status:id==='a'?'stage_review':'needs_changes',stages:id==='c'?undefined:[{stage:'几何',status:id==='a'?'sampled_pass':'needs_changes',explanation:'局部面积检查'},{stage:'投影',status:'sampled_pass'}]},current_applies:id!=='c',current:{decision:'accepted_with_exceptions'}}:
        {kind:'adapt',status:'succeeded',result:{artifact_sha256:id}}};
    };
    createCohortStatus(document.querySelector('main'),{groups:[{job_id:'source',source_sha256:'sourcehash',label:'reach',targets:['a','b','c'].map(job_id=>({job_id,artifact_sha256:job_id,label:job_id}))}],coverage:{expected:4,available:3,missing:[{motion:'squat',character:'d',status:'failed'}]}},(mi,ci)=>window.selected=[mi,ci]);
  });
  await page.getByRole('button',{name:'核对全部候选状态'}).click();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('已读取 3/3'));
  const status=await page.getByRole('status').innerText();assert(status.includes('技术通过 1/4'));assert(status.includes('有效阶段接受 2/4'));
  assert((await page.locator('tbody').innerText()).includes('旧结论已过期'));
  await page.getByLabel('按检查阶段筛选').selectOption('几何');
  assert.equal(await page.locator('tbody tr').count(),3);
  assert.equal(await page.getByRole('status').innerText(),status);
  await page.getByText('几何：需处理',{exact:true}).click();await page.getByText('局部面积检查',{exact:true}).waitFor();
  await page.getByLabel('按检查阶段筛选').selectOption('投影');
  assert.equal(await page.locator('tbody tr').count(),2); // Legacy evidence and missing candidate stay visible.
  await page.getByLabel('按检查阶段筛选').selectOption('');
  await page.getByLabel('仅显示异常或未验收').check();assert.equal(await page.locator('tbody tr').count(),3);
  await page.getByRole('button',{name:'检查此项'}).first().click();assert.deepEqual(await page.evaluate(()=>selected),[0,1]);
  await page.evaluate(()=>window.stale=true);await page.getByRole('button',{name:'核对全部候选状态'}).click();
  await page.getByText('无法核对：检查身份不匹配',{exact:true}).waitFor();assert((await page.getByRole('status').innerText()).includes('有效阶段接受 1/4'));
  assert.equal(await page.getByText('几何：需处理',{exact:true}).count(),0);
  assert((await page.evaluate(()=>calls)).every(c=>c.method==='GET'));
  await page.evaluate(()=>window.dispatchEvent(new CustomEvent('motion-stage-review-saved',{detail:{jobId:'a'}})));
  assert((await page.getByRole('status').innerText()).includes('有效阶段接受 0/4'));
  await page.getByText('结论已更新，请重新核对',{exact:true}).waitFor();
  await page.evaluate(()=>{
    window.fetch=(_url,{signal})=>new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true}));
  });
  await page.getByRole('button',{name:'核对全部候选状态'}).click();
  await page.getByRole('button',{name:'停止核对'}).click();
  assert.equal(await page.getByRole('button',{name:'核对全部候选状态'}).isEnabled(),true);
  assert((await page.getByRole('status').innerText()).includes('已读取 0/3'));
  assert.equal(await page.locator('tbody details').count(),0);
  console.log(JSON.stringify({passed:true,scope:'stage filtering and reasons, unchanged denominators, legacy unknowns, read-only counts, stale evidence and same-page selection'}));
}finally{await browser.close();}
