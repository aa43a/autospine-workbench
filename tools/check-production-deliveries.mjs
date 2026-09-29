import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:chrome,headless:true});
try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],requests=[];
  page.on('pageerror',e=>errors.push(String(e)));
  const job={job_id:'delivery-'+'a'.repeat(32),revision:4,status:'needs_review',step:'review',visual_status:'not_reviewed',request:{sources:[{run_id:'one'},{run_id:'two'}]},runtime:{frames:6,geometry_status:'passed'}};
  // UI-only fixture: it never writes a review or delivery into the real service.
  await page.route('**/api/production-deliveries**',async route=>{
    requests.push({method:route.request().method(),url:route.request().url()});
    assert.equal(route.request().method(),'GET');
    await route.fulfill({json:{deliveries:[job]}});
  });
  await page.goto('http://127.0.0.1:8918/production.html');
  await page.getByRole('heading',{name:'多动作交付包',exact:true}).waitFor();
  const panel=page.locator('#deliveries');
  await panel.getByText('记录整包验收',{exact:true}).click();
  await panel.getByLabel('动作、时间与异常（可选）').fill('UI-only draft at 1.2s');
  await page.waitForTimeout(5500);
  assert.equal(await panel.getByLabel('动作、时间与异常（可选）').inputValue(),'UI-only draft at 1.2s');
  assert.match(await panel.getByRole('link',{name:'下载 Spine 多动作候选'}).getAttribute('href'),/\/download$/);
  assert.equal(await panel.getByRole('button',{name:'阶段可接受，保留限制'}).count(),1);
  assert.equal(await panel.getByRole('button',{name:'记录需要修改'}).count(),1);
  await panel.screenshot({path:path.join(output,'delivery-card.png')});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({passed:true,scope:'UI fixture only',real_review_saved:false,errors,requests},null,2));
  console.log('Delivery UI fixture passed; no real review saved.');
}finally{await browser.close();}
