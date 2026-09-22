// Inspect actual workbench geometry counterfactuals without changing a candidate.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [base,jobId,output,dependencies]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try {
  const page=await browser.newPage({viewport:{width:1400,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(new URL('/motions.html#'+jobId,base).href);
  const card=page.locator('#'+jobId);
  await card.getByRole('button',{name:'检查可用范围与待处理项',exact:true}).click();
  await card.getByRole('button',{name:'查看变形区域与处理方案',exact:true}).waitFor({timeout:120000});
  const responsePromise=page.waitForResponse(r=>r.url().endsWith('/'+jobId+'/view/geometry-details.json'));
  await card.getByRole('button',{name:'查看变形区域与处理方案',exact:true}).click();
  const report=await (await responsePromise).json();
  const detail=report.rows[0].details[0];
  assert.ok(Number.isFinite(detail.without_deform_setup_ratio));
  assert.ok(Math.abs(detail.setup_ratio-detail.without_deform_setup_ratio-detail.deform_area_delta_ratio)<1e-12);
  await card.getByText(/同时刻移除局部 deform 后/).first().waitFor();
  await card.getByLabel('投影与局部形状对照').filter({hasText:'三角形主方向伸缩'}).first().waitFor();
  assert.ok(Number.isFinite(detail.shape_evidence.actual.minimum_stretch));
  await card.getByRole('combobox',{name:report.rows[0].slot+' 异常区域'}).selectOption('1');
  assert.equal(report.selected,false);
  assert.deepEqual(errors,[]);
  await fs.mkdir(output,{recursive:true});
  await card.screenshot({path:path.join(output,'comparison.png')});
  await fs.writeFile(path.join(output,'details.json'),JSON.stringify(report));
  await fs.writeFile(path.join(output,'check.json'),JSON.stringify({passed:true,jobId,artifact:report.artifact_sha256,errors,
    scope:'live_readonly_counterfactual_display_not_repair_or_acceptance'},null,2));
  console.log(JSON.stringify({passed:true,triangle:detail.triangle,before:detail.without_deform_setup_ratio,after:detail.setup_ratio}));
} finally {await browser.close();}
