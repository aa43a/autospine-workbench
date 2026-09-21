// Read-only real delivery check. Reject every non-GET request.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const report=await fs.readFile(process.argv[2],'utf8');
const url=report.match(/href="(http:\/\/127\.0\.0\.1:8918\/motion-cohort\.html#[^"]+)"/)?.[1];
assert.ok(url,'report must contain an exact-candidate review pack');
const browser=await chromium.launch({channel:'chrome',headless:true});
try {
  const page=await browser.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{
    assert.equal(route.request().method(),'GET','read-only verification');
    return route.continue();
  });
  await page.goto(url);
  const ready=page.getByText('已核对版本。查看角色动作后，可直接在本页保存阶段结论；不会自动确认。',{exact:true});
  await ready.waitFor({timeout:120000});
  const count=await page.locator('#motion option').count();assert.equal(count,8);
  const checked=[];
  for(let i=0;i<count;i++){
    if(i){await page.locator('#motion').selectOption(String(i));await ready.waitFor({timeout:120000});}
    assert.equal(await page.locator('#character option').count(),3);
    assert.equal(await page.locator('#time').isEnabled(),true);
    const frame=page.frameLocator('iframe');
    await frame.locator('canvas').waitFor({timeout:120000});
    await page.getByRole('button',{name:'记录 / 查看阶段验收'}).click();
    await page.getByLabel('阶段验收结论').waitFor({timeout:120000});
    checked.push(await page.locator('#target-title').textContent());
  }
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,real_sources:8,real_target_pages:8,review_reads:8,decisions_written:0,checked}));
}finally{await browser.close();}
