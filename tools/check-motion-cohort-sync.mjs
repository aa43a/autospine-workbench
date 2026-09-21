// Read-only live six-cell playback check. No review decisions are submitted.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE);
const state=JSON.parse(await fs.readFile('../tmp/m4-motion-center/cohort-state-v3.json','utf8'));
const groups=['squat','reach'].map(label=>({label,job_id:state.sources[label].job_id,
  source_sha256:state.sources[label].source_sha256,targets:['alice','huiye','hongmeiling'].map(character=>{
    const row=state.cells[label+'/'+character];
    return {label:character,job_id:row.job_id,artifact_sha256:row.result.artifact_sha256};
  })}));
const pack={version:1,plan_sha256:state.plan_sha256,groups};
const url='http://127.0.0.1:8918/motion-cohort.html#'+encodeURIComponent(JSON.stringify(pack));
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,
  args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
  const page=await browser.newPage(),errors=[],checked=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.route('**/api/**',route=>{
    assert.equal(route.request().method(),'GET','must not save decisions');return route.continue();
  });
  await page.goto(url);
  for(let mi=0;mi<2;mi++)for(let ci=0;ci<3;ci++){
    if(ci===0&&mi>0)await page.selectOption('#motion',String(mi));
    if(ci>0)await page.selectOption('#character',String(ci));
    await page.waitForFunction(()=>document.querySelector('#sync-status').textContent.startsWith('共用时间轴'),{},{timeout:120000});
    const end=await page.locator('#time').evaluate(e=>Number(e.max));
    for(const t of [end*.7,end*.2,0]){
      await page.locator('#time').evaluate((e,t)=>{e.value=t;e.dispatchEvent(new Event('input'));},t);
      const target=await page.locator('#target iframe').evaluate(e=>e.contentWindow.characterPlayerState);
      assert.ok(Math.abs(target.time-t)<.002);assert.equal(target.playing,false);
    }
    checked.push(groups[mi].label+'/'+groups[mi].targets[ci].label);
  }
  assert.deepEqual(errors,[]);
  await fs.mkdir('../tmp/m4-motion-center/sync-check-v1',{recursive:true});
  await page.screenshot({path:'../tmp/m4-motion-center/sync-check-v1/screen.png',fullPage:true});
  await fs.writeFile('../tmp/m4-motion-center/sync-check-v1/report.json',JSON.stringify({checked,errors,url},null,2));
  console.log(JSON.stringify({checked,errors}));
}finally{await browser.close();}
