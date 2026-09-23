// Read-only verification of the actual workbench restriction check.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [base,jobId,output,dependencies]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try {
  const page=await browser.newPage({viewport:{width:1400,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(new URL('/motions.html#'+jobId,base).href);
  const card=page.locator('#'+jobId);
  await card.getByRole('button',{name:'检查可用范围与待处理项',exact:true}).click();
  await card.getByRole('button',{name:'查看变形区域与处理方案',exact:true}).click({timeout:120000});
  const response=page.waitForResponse(r=>r.url().endsWith('/'+jobId+'/view/repair-feasibility.json'));
  await card.getByRole('button',{name:'检查局部修复限制',exact:true}).first().click();
  const result=await response;assert.equal(result.status(),200);
  const report=await result.json();const row=report.rows.find(r=>r.status==='fixed_vertex_counterexample');
  assert.ok(row);assert.equal(report.selected,false);
  await card.getByText(/当前策略固定单骨顶点：/).first().waitFor();
  await card.getByText(/扣除单骨整体变换后的面积比/).first().waitFor();
  assert.equal(row.worst.shape_evidence.reference_kind,'single_bone_affine');
  const link=card.getByRole('link',{name:/定位限制/}).first();
  assert.equal(Number(new URL(await link.getAttribute('href'),base).searchParams.get('time')),row.worst.time);
  assert.deepEqual(errors,[]);
  await fs.mkdir(output,{recursive:true});
  await card.screenshot({path:path.join(output,'feasibility.png')});
  await fs.writeFile(path.join(output,'check.json'),JSON.stringify({passed:true,jobId,report,errors,
    scope:'actual_workbench_readonly_check_and_locator_url_not_visual_acceptance'},null,2));
  console.log(JSON.stringify({passed:true,triangles:row.counterexample_count,times:row.failed_times,time:row.worst.time}));
} finally {await browser.close();}
