// Read-only inspection of synchronized isolated candidates, never saves acceptance.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [url,dependencies,chrome,output]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
  const page=await browser.newPage({viewport:{width:1600,height:1200}}),errors=[],checked=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(url);const inventory=await (await page.request.get(new URL('comparison.json',url).href)).json();
  async function ready(){await page.waitForFunction(()=>window.reachComparisonState?.ready||window.reachComparisonError,null,{timeout:120000});assert.equal(await page.evaluate(()=>window.reachComparisonError),undefined);}
  async function seek(t){await page.locator('#seek').evaluate((s,t)=>{s.value=t;s.dispatchEvent(new Event('input'));},t);}
  for(let i=0;i<inventory.rows.length;i++){
    await page.selectOption('#character',String(i));await ready();
    const states=()=>page.evaluate(()=>['left','right'].map(id=>document.getElementById(id).contentWindow.characterPlayerState));
    assert.deepEqual((await page.evaluate(()=>window.reachComparisonState)).artifacts,inventory.rows[i].views.map(v=>v.artifact));
    const initial=await page.frames().find(f=>f.url().includes(`/${i}/yaw-0/`)).locator('canvas').screenshot();
    const d=(await states())[0].duration;await seek(d*.6);
    assert.ok((await states()).every(s=>Math.abs(s.time-d*.6)<.002));
    await seek(0);
    assert.deepEqual(await page.frames().find(f=>f.url().includes(`/${i}/yaw-0/`)).locator('canvas').screenshot(),initial);
    await page.click('#play');await page.waitForTimeout(300);await page.click('#play');
    const after=await states();assert.ok(after[0].time>0);assert.equal(after[0].time,after[1].time);
    checked.push({job:inventory.rows[i].job,synchronized:true,reverse_seek:true,play_pause:true});
  }
  await page.selectOption('#character','0');await ready();await seek(2.4);
  await fs.mkdir(output,{recursive:true});await page.screenshot({path:path.join(output,'reach-comparison.png'),fullPage:true});
  assert.deepEqual(errors,[]);await fs.writeFile(path.join(output,'check.json'),JSON.stringify({checked,errors,authority:'none'},null,2));
  console.log(JSON.stringify({passed:true,characters:checked.length}));
}finally{await browser.close();}
