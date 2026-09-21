// Read-only check of the live operator panel and its candidate-bound endpoint.
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const id=process.argv[2];
if(!/^motion-[a-f0-9]{32}$/.test(id||''))throw Error('Exact job id required');
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
  const page=await browser.newPage();
  await page.goto('http://127.0.0.1:8918/motions.html#'+id);
  const card=page.locator('#'+id);
  const reply=page.waitForResponse(r=>r.url().endsWith(`/${id}/view/depth-status.json`),{timeout:120000});
  await card.getByRole('button',{name:'在此查看遮挡状态'}).click();
  const response=await reply; assert.equal(response.status(),200);
  const report=await response.json(); assert.equal(report.authority,'none');
  const filter=card.getByLabel('显示记录：');
  await filter.waitFor();
  for(const category of ['depth_conflict','resource_limit','unsupported_check']){
    await filter.selectOption(category);
    const section=filter.locator('xpath=../..');
    const expected=(report.records_by_category?.[category]||report.records.filter(r=>r.category===category)).slice(0,20);
    assert.equal(await section.getByRole('link',{name:/^定位 /}).count(),expected.length);
    if(expected.some(r=>r.model_evidence)){
      assert.ok((await section.textContent()).includes('不等于已观察到画面错误'));
    }
    if(category==='resource_limit'&&expected.length){
      assert.ok((await section.textContent()).includes('此处未测量，不计作画面错误'));
    }
    for(const row of expected){
      assert.ok(await section.locator(`a[href="/api/motions/${id}/view/player.html?time=${row.time}"]`).count());
    }
  }
  await filter.selectOption('all');
  console.log(JSON.stringify({passed:true,status:report.status,counts:report.failure_record_counts,artifact:report.artifact_sha256}));
}finally{await browser.close();}
