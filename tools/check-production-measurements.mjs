import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome,run]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],writes=[];
 page.on('pageerror',e=>errors.push(String(e)));
 page.on('request',r=>{if(r.method()==='POST'&&r.url().includes('work-sessions'))writes.push(r.url());});
 await page.goto(`http://127.0.0.1:8918/production.html?run=${run}`);
 const panel=page.locator('#measurements');await panel.getByText(/本次已记录人工操作：尚未计时/).waitFor();
 await panel.getByRole('button',{name:'刷新耗时统计'}).click();
 await panel.getByText('本次制作人工工作计时 · 已暂停',{exact:true}).click();
 await panel.getByRole('button',{name:'开始本阶段计时'}).waitFor();
 const report=await (await page.request.get(`http://127.0.0.1:8918/api/production/${run}/metrics`)).json();
 assert.equal(report.human.recorded_minutes,null);assert.equal(report.human.total_human_minutes,null);
 assert.ok(report.recorded_execution_seconds>0);assert.equal(report.automatic_compute_seconds,null);
 assert.equal(report.intervention_count,null);
 await panel.screenshot({path:path.join(output,'measurements.png')});
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
 await fs.writeFile(path.join(output,'report.json'),JSON.stringify({passed:true,run,metrics:report,errors,operator_records_written:false},null,2));
 console.log(JSON.stringify({passed:true,run,recorded_execution_seconds:report.recorded_execution_seconds}));
}finally{await browser.close();}
