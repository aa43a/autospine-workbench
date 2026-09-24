import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const [base, dependency, output]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(dependency));
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try {
  const page=await browser.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(base+'/motions.html');
  const select=page.getByLabel('姿态策略',{exact:true});
  await select.selectOption('source-pose-post-contact-timeline-v2');
  const result=await page.evaluate(async()=>{
    const module=await import('/modules/motion-pose-selection.js');
    const value=document.querySelector('select[aria-label="姿态策略"]').value;
    const panel=document.createElement('section');document.body.append(panel);
    module.appendPoseSummary(panel,{job_id:'read-only-history',result:{pose_profile:module.LEGACY_POST_CONTACT_PROFILE}});
    return {selection:module.poseSelection(value,{}),history:panel.textContent};
  });
  assert.equal(result.selection.pose_profile,'source-pose-post-contact-timeline-v2');
  assert.match(result.history,/历史策略/);assert.match(result.history,/最终时间轴接触复核/);
  assert.deepEqual(errors,[]);
  await fs.mkdir(output,{recursive:true});
  await fs.writeFile(output+'/report.json',JSON.stringify({passed:true,...result,errors,
    scope:'live_selection_and_legacy_display_no_task_submitted'},null,2));
  console.log(JSON.stringify({passed:true,...result}));
}finally {await browser.close();}
