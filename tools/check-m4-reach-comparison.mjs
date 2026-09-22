// Read-only inspection of synchronized isolated candidates, never saves acceptance.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [url,dependencies,chrome,output,diagnosticTimes='',cameraCrop='']=process.argv.slice(2);
const probes=diagnosticTimes?diagnosticTimes.split(',').map(Number):[];
assert.ok(probes.length<=16&&probes.every(t=>Number.isFinite(t)&&t>=0));
const crop=cameraCrop?cameraCrop.split(',').map(Number):null;
if(crop)assert.ok(crop.length===4&&crop.every(Number.isFinite)&&crop[2]>0&&crop[3]>0);
const {chromium}=await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
  const page=await browser.newPage({viewport:{width:1600,height:1200}}),errors=[],checked=[];
  page.on('pageerror',e=>errors.push(String(e)));
  if(crop)await page.route('**/player-assets/scene.json',async route=>{
    const response=await route.fetch(),scene=await response.json();
    [scene.info.left,scene.info.bottom,scene.info.width,scene.info.height]=crop;
    await route.fulfill({response,json:scene});
  });
  await page.goto(url);const inventory=await (await page.request.get(new URL('comparison.json',url).href)).json();
  await fs.mkdir(output,{recursive:true});
  async function ready(){await page.waitForFunction(()=>window.reachComparisonState?.ready||window.reachComparisonError,null,{timeout:120000});assert.equal(await page.evaluate(()=>window.reachComparisonError),undefined);
    if(crop)for(const frame of page.frames().filter(f=>f.url().includes('/runtime/player.html')))
      await frame.addStyleTag({content:'canvas{width:500px!important;height:500px!important;image-rendering:pixelated}'});
  }
  async function seek(t){await page.locator('#seek').evaluate((s,t)=>{s.value=t;s.dispatchEvent(new Event('input'));},t);}
  for(let i=0;i<inventory.rows.length;i++){
    await page.selectOption('#character',String(i));await ready();
    const states=()=>page.evaluate(()=>['left','right'].map(id=>document.getElementById(id).contentWindow.characterPlayerState));
    assert.deepEqual((await page.evaluate(()=>window.reachComparisonState)).artifacts,inventory.rows[i].views.map(v=>v.artifact));
    const leftFrame=()=>page.frameLocator('#left');
    const initial=await leftFrame().locator('canvas').screenshot();
    const d=(await states())[0].duration;await seek(d*.6);
    assert.ok((await states()).every(s=>Math.abs(s.time-d*.6)<.002));
    await seek(0);
    assert.deepEqual(await leftFrame().locator('canvas').screenshot(),initial);
    await page.click('#play');await page.waitForTimeout(300);await page.click('#play');
    const after=await states();assert.ok(after[0].time>0);assert.equal(after[0].time,after[1].time);
    await seek(d*.6);
    await page.screenshot({path:path.join(output,`character-${i}-comparison.png`),fullPage:true});
    checked.push({job:inventory.rows[i].job,synchronized:true,reverse_seek:true,play_pause:true});
  }
  await page.selectOption('#character','0');await ready();await seek(2.4);
  await fs.mkdir(output,{recursive:true});await page.screenshot({path:path.join(output,'reach-comparison.png'),fullPage:true});
  for(const time of probes){await seek(time);assert.ok(Math.abs((await page.evaluate(()=>window.reachComparisonState)).time-time)<.002);
    await page.screenshot({path:path.join(output,`diagnostic-${time}.png`),fullPage:true});}
  assert.deepEqual(errors,[]);await fs.writeFile(path.join(output,'check.json'),JSON.stringify({checked,errors,diagnostic_times:probes,camera_crop:crop,authority:'none'},null,2));
  const jumpIndex=String(Math.min(1,inventory.rows.length-1));
  const jump=new URL(url);jump.searchParams.set('character',jumpIndex);jump.searchParams.set('time','1.25');
  await page.goto(jump.href);await ready();
  assert.equal(await page.locator('#character').inputValue(),jumpIndex);
  assert.equal((await page.evaluate(()=>window.reachComparisonState)).time,1.25);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,characters:checked.length}));
}finally{await browser.close();}
