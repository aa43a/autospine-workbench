import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
  const page=await browser.newPage();
  for(const id of ['motion-8ca66333718c4e9698c2de4261be5878','motion-07cd3c09f104427689fc6773db28269b','motion-223847a1e58e45cfa2d7764ccc6ef282']){
    await page.goto('http://127.0.0.1:8918/motions.html#'+id);
    const card=page.locator('#'+id);
    await card.getByRole('button',{name:'在此查看遮挡状态'}).click();
    const reply=page.waitForResponse(r=>r.url().endsWith('/local-depth-status.json'));
    await card.getByRole('button',{name:'查看局部深度补充检查'}).click();
    const response=await reply;assert.equal(response.status(),200);
    const report=await response.json();assert.equal(report.reports.length,1);assert.equal(report.selected,false);
    const summary=card.getByText('逐像素检查 · 源动作帧',{exact:true});
    await summary.click();
    const section=summary.locator('..');
    assert.equal(await section.getByRole('link',{name:/定位/}).count(),report.reports[0].records.length);
    assert.ok((await card.textContent()).includes('补充检查不改变当前候选'));
    if(id.includes('223847'))assert.ok((await section.textContent()).includes('未测：depth_overlap_pixel_budget 55 项'));
    console.log(JSON.stringify({id,passed:true,evidence:report.reports[0].evidence_sha256}));
  }
}finally{await browser.close();}
