// UI-only fixtures. POSTs are intercepted: no real task or acceptance is written.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome,run]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:chrome,headless:true});
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),writes=[],errors=[];
 page.on('pageerror',e=>errors.push(String(e)));
 const original=await (await page.request.get(`http://127.0.0.1:8918/api/production/${run}`)).json();
 const registration='a'.repeat(64),child='job:motion-'+'b'.repeat(32);
 const candidates=[registration,child].map((selector,i)=>({selector,artifact_sha256:String(i+1).repeat(64),kind:i?'repair_job':'registered_candidate',player_url:'/fixture-player-'+i}));
 await page.route(`**/api/production/${run}/body-candidates`,r=>r.fulfill({json:{baseline_sha256:original.stages.body.artifact_sha256,rows:candidates,unavailable:[]}}));
 let release=null;
 await page.route(`**/api/production/${run}/revision-plan`,async route=>{const request=route.request().postDataJSON();writes.push({route:'plan',request});if(release)await new Promise(resolve=>{release.resolve=resolve;});await route.fulfill({json:{plan_sha256:'fixture-plan',reuse_stages:['character','body'],refresh_stages:[],rebuild_stages:['joint']}});});
 await page.route(`**/api/production/${run}/revise`,route=>{writes.push({route:'revise',request:route.request().postDataJSON()});return route.fulfill({json:{run_id:run}});});
 await page.goto(`http://127.0.0.1:8918/production.html?run=${run}`);
 const panel=page.locator('#revision-panel'),select=panel.getByRole('combobox',{name:'身体修复版本'});
 await page.waitForFunction(()=>{const s=document.querySelector('[aria-label="身体修复版本"]');return s&&!s.disabled;});
 await select.selectOption(registration);
 await panel.getByRole('button',{name:'预览受影响步骤'}).click();
 await panel.getByRole('button',{name:'按此范围创建修正任务'}).waitFor();
 assert.equal(writes.at(-1).request.body_registration,registration);
 // A selection change while preview is pending must invalidate its response.
 await select.selectOption(child);release={};
 await panel.getByRole('button',{name:'预览受影响步骤'}).click();
 while(!release.resolve)await new Promise(r=>setTimeout(r,25));
 await select.selectOption('');const done=release.resolve;release=null;done();
 await panel.getByRole('button',{name:'预览受影响步骤'}).waitFor();
 await page.waitForFunction(()=>!document.querySelector('#revision-panel button:disabled'));
 assert.equal(await panel.getByRole('button',{name:'按此范围创建修正任务'}).count(),0);
 await select.selectOption(child);
 await panel.getByRole('button',{name:'预览受影响步骤'}).click();
 await panel.getByRole('button',{name:'按此范围创建修正任务'}).click();
 assert.equal(writes.at(-1).route,'revise');assert.equal(writes.at(-1).request.body_registration,child);
 assert.equal(writes.at(-1).request.expected_plan_sha256,'fixture-plan');
 assert.deepEqual(errors,[]);
 await fs.writeFile(path.join(output,'report.json'),JSON.stringify({passed:true,scope:'UI fixtures only; all production POSTs intercepted',writes,errors,real_builds_created:false},null,2));
 console.log(JSON.stringify({passed:true,scope:'ui-fixture'}));
}finally{await browser.close();}
