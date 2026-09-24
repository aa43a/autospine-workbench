import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const [base,job,repair]=process.argv.slice(2);
const sampleCount=process.env.LOCAL_DEPTH_SAMPLE_COUNT?Number(process.env.LOCAL_DEPTH_SAMPLE_COUNT):null;
const profile=process.env.LOCAL_DEPTH_PROFILE;
assert.ok(sampleCount===null||Number.isInteger(sampleCount)&&sampleCount>0);
const browser=await chromium.launch({channel:'chrome',headless:true,
 args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(`${base}/motions.html#${job}`);const card=page.locator('#'+job);
 await card.getByRole('button',{name:'在此查看遮挡状态',exact:true}).click();
 const response=page.waitForResponse(r=>r.url().endsWith(`/${job}/view/local-depth-status.json`));
 await card.getByRole('button',{name:'查看局部深度补充检查',exact:true}).click();
 const report=await (await response).json();const evidence=report.reports.find(r=>r.records.length&&
   (sampleCount===null||r.requested_sample_times?.length===sampleCount)&&(!profile||r.profile===profile));
 assert.ok(evidence);const row=evidence.records[0];
 const details=card.locator(`details[data-depth-evidence="${evidence.evidence_sha256}"]`);
 await details.locator('summary').click();
 if(evidence.sleeve_helpers)assert.ok((await details.innerText()).includes('不代表观测到真实布料深度'));
 const link=details.getByRole('link',{name:`定位 ${row.time.toFixed(3)} 秒`,exact:true}).first();
 assert.equal(await card.locator('iframe').count(),0);
 await link.click();
 await page.waitForFunction(({job,pair,time})=>{
   const win=document.getElementById(job)?.querySelector('iframe')?.contentWindow;
   return win?.characterPlayerState?.time===time&&JSON.stringify(win.characterInspectionState?.regions)===JSON.stringify(pair);
 },{job,pair:row.pair,time:row.time},{timeout:120000});
 assert.equal(page.context().pages().length,1);
 assert.equal(await card.locator('iframe').evaluate(f=>f.contentWindow.characterPlayerControl.artifact),report.artifact_sha256);
 await card.getByRole('button',{name:'同步源骨架对照',exact:true}).click();
 await card.getByText('共用时间轴；骨架显示最近源采样，观察视角不修改角色动画。',{exact:true}).waitFor();
 const slider=card.getByRole('slider',{name:'源与角色共用时间轴',exact:true});
 const moved=await slider.evaluate(el=>{const start=Number(el.min),end=Number(el.max);el.value=String(start+(end-start)/2);el.dispatchEvent(new Event('input'));return Number(el.value)-start;});
 assert.ok(Math.abs(await card.locator('iframe').evaluate(f=>f.contentWindow.characterPlayerState.time)-moved)<.002);
 assert.deepEqual(await card.locator('iframe').evaluate(f=>f.contentWindow.characterInspectionState.regions),row.pair);
 await link.click();
 await card.getByRole('button',{name:'显示完整角色',exact:true}).click();
 assert.deepEqual(await card.locator('iframe').evaluate(f=>f.contentWindow.characterInspectionState.regions),[]);
 assert.equal(await card.locator('iframe').evaluate(f=>f.contentWindow.characterPlayerState.time),row.time);
 await card.locator('iframe').evaluate(f=>{f.contentWindow.characterPlayerControl={artifact:'wrong',seek:()=>{throw Error('wrong candidate controlled');}};});
 await link.click();await card.getByText('定位未完成：候选身份不一致，请刷新任务',{exact:true}).waitFor();
 if(repair){
   await page.goto(`${base}/motions.html#${repair}`);
   const repaired=page.locator('#'+repair);
   await repaired.getByRole('button',{name:'在此查看遮挡状态',exact:true}).click();
   await repaired.getByRole('button',{name:'查看局部深度补充检查',exact:true}).waitFor();
 }
 assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,job,repair,sampleCount,time:row.time,pair:row.pair,
   profile:evidence.profile,evidence:evidence.evidence_sha256,
   checks:['same_page','lazy_load','source_timeline_preserves_pair','identity_guard','restore_full_at_same_time',...(repair?['repair_entry_visible']:[])]}));
}finally{await browser.close();}
