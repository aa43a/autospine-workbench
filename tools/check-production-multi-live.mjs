import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome,job]=process.argv.slice(2);
assert.match(job,/^delivery-[a-f0-9]{32}$/);
await fs.mkdir(output,{recursive:true});
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
  page.setDefaultTimeout(120000);page.on('pageerror',e=>errors.push(String(e)));
  const base=`http://127.0.0.1:8918/api/production-deliveries/${job}`;
  const before=await (await page.request.get(base)).json();
  assert.ok(['needs_review','stage_accepted'].includes(before.status));
  await page.goto('http://127.0.0.1:8918/production.html');
  const card=page.locator('#deliveries article').filter({has:page.locator(`a[href="/api/production-deliveries/${job}/download"]`)});
  await card.getByRole('button',{name:'在本页播放多动作'}).click();
  const frame=await (await page.locator('#delivery-player').elementHandle()).contentFrame();
  await frame.waitForFunction(()=>window.characterPlayerReady===true,{},{timeout:120000});
  assert.equal(await frame.evaluate(()=>window.characterPlayerControl.artifact),before.artifact_sha256);
  const names=await frame.locator('#motion option').evaluateAll(options=>options.map(o=>o.value));
  assert.ok(names.length>=2);
  const checked=[];
  for(const name of names){
    await frame.locator('#motion').selectOption(name);
    const duration=Number(await frame.locator('#time').getAttribute('max'));
    assert.ok(duration>0);
    await frame.locator('#time').evaluate((slider,value)=>{slider.value=String(value);slider.dispatchEvent(new Event('input',{bubbles:true}));},duration*.5);
    assert.ok(Math.abs(Number(await frame.locator('#time').inputValue())-duration*.5)<.02);
    await frame.locator('#play').click();
    await frame.waitForFunction(t=>Number(document.getElementById('time').value)>t, duration*.5+.02);
    await frame.locator('#play').click();
    checked.push({name,duration,seek_and_play:true});
  }
  const response=await page.request.get(base+'/download',{timeout:120000});assert.equal(response.status(),200);
  const bytes=await response.body();assert.equal(bytes.subarray(0,2).toString(),'PK');
  await fs.writeFile(path.join(output,'candidate.zip'),bytes);
  await page.locator('#delivery-player').screenshot({path:path.join(output,'player.png')});
  const after=await (await page.request.get(base)).json();assert.equal(after.revision,before.revision);
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({passed:true,job,artifact_sha256:before.artifact_sha256,animations:checked,download_bytes:bytes.length,review_saved:false,errors},null,2));
  console.log(JSON.stringify({passed:true,animations:checked,download_bytes:bytes.length}));
}finally{await browser.close();}
