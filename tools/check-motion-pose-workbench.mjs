// Read-only verification of the real source-pose workbench job.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE);
const job='motion-138be48a1c004545a4895225ead2074e';
const artifact='e05acddc5601c29bdd508931c794282979f8c5f2bdeec822a86bb352a5a74873';
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,
 args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
 const page=await browser.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(String(e)));
 await page.route('**/api/**',route=>{assert.equal(route.request().method(),'GET');return route.continue();});
 await page.goto('http://127.0.0.1:8918/motions.html#'+job);
 const card=page.locator(`[data-job-id="${job}"]`);
 await card.getByText('姿态策略：源姿态与髋中心（实验候选）',{exact:false}).waitFor({timeout:120000});
 assert.match(await card.textContent(),/几何：需调整/);
 assert.equal(await page.getByLabel('姿态策略',{exact:true}).count(),1);
 const link=card.getByRole('link',{name:'查看姿态与修正依据'});
 const response=await page.request.get('http://127.0.0.1:8918'+await link.getAttribute('href'));
 assert.equal(response.status(),200);
 await page.goto(`http://127.0.0.1:8918/api/motions/${job}/view/player.html?time=0.9333335`);
 await page.waitForFunction(()=>window.characterPlayerReady,{},{timeout:120000});
 assert.equal(await page.evaluate(()=>window.characterPlayerControl.artifact),artifact);
 assert.equal(await page.evaluate(()=>window.characterPlayerState.time),.9333335);
 assert.deepEqual(errors,[]);
 const out='../tmp/m4-motion-center/pose-workbench-v1';await fs.mkdir(out,{recursive:true});
 await page.screenshot({path:out+'/player.png',fullPage:true});
 await fs.writeFile(out+'/report.json',JSON.stringify({job,artifact,passed:true,errors},null,2));
 console.log(JSON.stringify({job,passed:true,errors}));
}finally{await browser.close();}
