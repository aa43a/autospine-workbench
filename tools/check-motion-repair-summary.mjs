// Regression for local, partition and material summaries in a real DOM.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const {chromium}=createRequire(process.argv[2]+'/package.json')('playwright-core');
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try {
  const page=await browser.newPage();await page.setContent('<main></main>');
  await page.addScriptTag({content:fs.readFileSync('web/modules/motion-repair-summary.js','utf8').replace('export async function','async function')});
  const row={slot:'arm',min_area_ratio:.3,max_edge_stretch:1.8,inversion_samples:0,sample_count:120};
  const report={artifact_sha256:'current',slot:'arm',parent_job_id:'parent',before:{records:[row]},after:{records:[row]}};
  for(const [kind,extra] of Object.entries({local:{},partition:{boundary:{status:'needs_changes',failed_times:2,sample_count:120,limit_px:2,worst:{time:1,gap_px:3}}},material:{material:{selected_triangles:[1,3],interval:[1,2]}}})) {
    const text=await page.evaluate(async report=>{
      const panel=document.querySelector('main');panel.replaceChildren();
      window.fetch=async()=>({ok:true,json:async()=>report});
      await appendRepairSummary(panel,{job_id:'test',result:{artifact_sha256:'current',repair_profile:'test'}});
      return panel.textContent;
    },{...report,...extra});
    assert(!text.includes('无法读取'),text);assert(text.includes('最小面积比 0.300'));
    if(kind==='partition')assert(text.includes('查看边界 1.000 秒'));
    if(kind==='material')assert(text.includes('换图不会修复投影方向错误'));
  }
  await page.evaluate(async()=>{document.querySelector('main').replaceChildren();await appendRepairSummary(document.querySelector('main'),{job_id:'test',result:{artifact_sha256:'wrong',repair_profile:'test'}});});
  assert((await page.locator('main').innerText()).includes('身份不匹配'));
  if(process.argv[3]&&process.argv[4]) {
    const base=process.argv[3],job=process.argv[4];await page.goto(base+'/motions.html#'+job);
    const result=await page.evaluate(async job=>{
      const response=await fetch('/api/motions/'+job);const body=await response.json();
      const value=body.job||body;
      const {appendRepairSummary}=await import('/modules/motion-repair-summary.js');
      const panel=document.createElement('section');document.body.prepend(panel);
      await appendRepairSummary(panel,value);return {text:panel.textContent,kind:value.kind};
    },job);
    assert(result.text.includes('区域换图候选前后'),result.text);
    assert(result.text.includes('换图不会修复投影方向错误'),result.text);
    assert(!result.text.includes('无法读取'),result.text);
    console.log(JSON.stringify({live_job:job,text:result.text}));
  }
  console.log(JSON.stringify({passed:true,scope:'browser summary rendering, 3 repair profiles and stale identity'}));
}finally{await browser.close();}
