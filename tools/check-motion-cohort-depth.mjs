import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const [base,sourceId,jobId]=process.argv.slice(2);
const get=async path=>{const response=await fetch(base+path);assert(response.ok);return response.json();};
const source=await get('/api/motions/'+sourceId),job=await get('/api/motions/'+jobId);
const pack={version:1,plan_sha256:'0'.repeat(64),groups:[{label:'diagnostic',job_id:sourceId,source_sha256:source.source_sha256,
 targets:[{label:job.project_id,job_id:jobId,artifact_sha256:job.result.artifact_sha256}]}]};
const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
 const page=await browser.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.goto(base+'/motion-cohort.html#'+encodeURIComponent(JSON.stringify(pack)));
 await page.waitForFunction(()=>document.querySelector('#target iframe')?.contentWindow?.characterPlayerControl,null,{timeout:120000});
 await page.getByRole('button',{name:'在此查看遮挡状态',exact:true}).click();
 const response=page.waitForResponse(r=>r.url().endsWith('/local-depth-status.json'));
 await page.getByRole('button',{name:'查看局部深度补充检查',exact:true}).click();
 const report=await(await response).json(),row=report.reports.find(r=>r.records.length).records[0];
 await page.locator('details').filter({has:page.locator('summary').filter({hasText:'逐像素检查'})}).first().locator('summary').click();
 await page.getByRole('link',{name:`定位 ${row.time.toFixed(3)} 秒`,exact:true}).first().click();
 const read=()=>page.locator('#target iframe').evaluate(f=>({time:f.contentWindow.characterPlayerState.time,regions:f.contentWindow.characterInspectionState.regions}));
 assert.deepEqual(await read(),{time:row.time,regions:row.pair});
 assert.equal(page.context().pages().length,1);
 await page.locator('#time').evaluate(el=>{el.value='1.5';el.dispatchEvent(new Event('input'));});
 assert.deepEqual(await read(),{time:1.5,regions:row.pair});
 await page.getByRole('button',{name:'显示完整角色',exact:true}).click();
 assert.deepEqual(await read(),{time:1.5,regions:[]});
 await page.locator('#target iframe').evaluate(f=>{f.contentWindow.characterPlayerControl={artifact:'wrong',inspectRegions:()=>{throw Error('stale controlled');}};});
 await page.getByRole('button',{name:'显示完整角色',exact:true}).click();
 assert.match(await page.locator('#sync-status').innerText(),/未启用/);
 assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,jobId,pair:row.pair,checks:['same_page_depth','timeline_keeps_pair','restore_same_frame','stale_identity']}));
}finally{await browser.close();}
