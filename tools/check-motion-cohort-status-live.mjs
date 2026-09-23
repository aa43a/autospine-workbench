// Read-only status verification for an exact frozen navigation pack.
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const {chromium}=createRequire(process.argv[2]+'/package.json')('playwright-core');
const folder=process.argv[3],url=(await fs.readFile(folder+'/url.txt','utf8')).trim();
const pack=JSON.parse(decodeURIComponent(new URL(url).hash.slice(1)));
assert.equal(pack.coverage.expected,24);assert.equal(pack.coverage.available,24);
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try{
  const page=await browser.newPage({viewport:{width:1400,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{assert.equal(route.request().method(),'GET');return route.continue();});
  await page.goto(url);
  await page.getByRole('button',{name:'核对全部候选状态'}).click();
  await page.waitForFunction(()=>!Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='核对全部候选状态')?.disabled,null,{timeout:300000});
  const panel=page.getByRole('region',{name:'固定集状态'});
  const summary=await panel.getByRole('status').innerText();assert(summary.includes('已读取 24/24'),summary);
  const rows=await panel.locator('tbody tr').allTextContents();assert.equal(rows.length,24);
  const stages={};
  for(const stage of ['投影','几何','接触','遮挡','Runtime']){
    await panel.getByLabel('按检查阶段筛选').selectOption(stage);
    stages[stage]=await panel.locator('tbody tr').count();
    assert.equal(await panel.getByRole('status').innerText(),summary);
    for(const row of await panel.locator('tbody tr').all())assert(!(await row.locator('summary').allTextContents()).includes(stage+'：限定采样通过'));
  }
  await panel.getByLabel('按检查阶段筛选').selectOption('');
  await panel.getByLabel('仅显示异常或未验收').check();
  await panel.getByRole('button',{name:'检查此项'}).first().click();
  await page.getByText('已核对版本。查看角色动作后，可直接在本页保存阶段结论；不会自动确认。',{exact:true}).waitFor({timeout:120000});
  await panel.screenshot({path:folder+'/matrix.png'});
  assert.deepEqual(errors,[]);
  const report={summary,stages,rows,selected:await page.locator('#target-title').innerText(),decisions_written:0,runtime_recaptured:false};
  await fs.writeFile(folder+'/report.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}finally{await browser.close();}
