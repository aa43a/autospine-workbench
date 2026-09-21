// Read-only live candidate workflow; no acceptance or retargeting requests.
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const id=process.argv[2];
if(!/^motion-[a-f0-9]{32}$/.test(id||''))throw Error('Exact job id required');
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
  const page=await browser.newPage();
  await page.goto('http://127.0.0.1:8918/motions.html#'+id);
  const card=page.locator('#'+id);
  await card.getByRole('button',{name:'检查可用范围与待处理项',exact:true}).click();
  const button=card.getByRole('button',{name:'在此比较可用视角',exact:true});await button.waitFor();
  assert.ok((await card.textContent()).includes('区间不确定不等于画面错误'));
  const reply=page.waitForResponse(r=>r.url().endsWith('/'+id+'/compare-targets'),{timeout:120000});
  await button.click();const response=await reply;assert.equal(response.status(),200);
  const report=await response.json();assert.equal(report.authority,'none');
  assert.ok(report.rows.some(row=>row.job_id===id));
  assert.equal(page.url(),'http://127.0.0.1:8918/motions.html#'+id);
  console.log(JSON.stringify({passed:true,comparisonCandidates:report.rows.length,recommended:report.recommended_job_id}));
}finally{await browser.close();}
