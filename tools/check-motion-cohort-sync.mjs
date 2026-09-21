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
    await page.locator('#time').evaluate((e,t)=>{e.value=t;e.dispatchEvent(new Event('input'));},end*.5);
    const before=await page.locator('#source').screenshot();
    await page.selectOption('#source-view','side');
    assert.notDeepEqual(await page.locator('#source').screenshot(),before);
    const sideTime=await page.locator('#target iframe').evaluate(e=>e.contentWindow.characterPlayerState.time);
    assert.ok(Math.abs(sideTime-end*.5)<.002,'view must preserve time');
    await page.selectOption('#source-view','');
    assert.deepEqual(await page.locator('#source').screenshot(),before,'source view restores exactly');
    checked.push(groups[mi].label+'/'+groups[mi].targets[ci].label);
  }
  await page.getByRole('button',{name:'比较该角色的已有视角候选'}).click();
  await page.getByRole('link',{name:'在当前页比较',exact:false}).first().click({timeout:120000});
  await page.waitForFunction(()=>[...document.querySelectorAll('#alternative p')].some(e=>e.textContent.startsWith('共用时间轴')),{},{timeout:120000});
  for(const t of [2.5,.5]){
    await page.locator('#time').evaluate((e,t)=>{e.value=t;e.dispatchEvent(new Event('input'));},t);
    for(const selector of ['#target iframe','#alternative iframe']){
      const actual=await page.locator(selector).evaluate(e=>e.contentWindow.characterPlayerState.time);
      assert.ok(Math.abs(actual-t)<.002,'both candidates share timeline');
    }
  }
  assert.deepEqual(errors,[]);
  await fs.mkdir('../tmp/m4-motion-center/sync-check-v1',{recursive:true});
  await page.screenshot({path:'../tmp/m4-motion-center/sync-check-v1/screen.png',fullPage:true});
  await fs.writeFile('../tmp/m4-motion-center/sync-check-v1/report.json',JSON.stringify({checked,errors,url},null,2));
  console.log(JSON.stringify({checked,errors}));
}finally{await browser.close();}
