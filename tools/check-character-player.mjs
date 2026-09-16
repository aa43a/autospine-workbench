// Opt-in browser validation against an existing, exact candidate. Does not save reviews.
import assert from 'node:assert/strict';
import path from 'node:path';
import fs from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const [url, dependencies, chrome, output] = process.argv.slice(2);
if (!output) throw Error('usage: url dependencies chrome output-directory');
const {chromium} = await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
const browser = await chromium.launch({executablePath:chrome,headless:true,
  args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
  const page = await browser.newPage({viewport:{width:1280,height:1000}}), errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(url,{timeout:300000});
  await page.waitForFunction(()=>window.characterPlayerReady||window.characterPlayerError,{}, {timeout:300000});
  assert.equal(await page.evaluate(()=>window.characterPlayerError),undefined);
  const animations=await page.locator('#motion option').evaluateAll(nodes=>nodes.map(n=>n.value));
  assert.ok(animations.length);
  const seek=async time=>page.locator('#time').evaluate((slider,value)=>{slider.value=value;slider.dispatchEvent(new Event('input'));},time);
  const checked=[];
  for(const animation of animations){
    await page.selectOption('#motion',animation);
    const initial=await page.locator('canvas').screenshot();
    const duration=await page.evaluate(()=>window.characterPlayerState.duration);
    await seek(duration/2);
    assert.ok(Math.abs((await page.evaluate(()=>window.characterPlayerState.time))-duration/2)<.002);
    await seek(0);
    assert.deepEqual(await page.locator('canvas').screenshot(),initial,'backward seek must restore the exact initial pose');
    await page.click('#play');await page.waitForTimeout(250);await page.click('#play');
    const stopped=await page.evaluate(()=>window.characterPlayerState);
    assert.ok(stopped.time>0);assert.equal(stopped.playing,false);
    checked.push({animation,duration,reverse_seek:true,play_pause:true});
  }
  await page.selectOption('#motion',animations.includes('walk')?'walk':animations[0]);
  await page.click('#reset');
  await fs.mkdir(output,{recursive:true});
  await page.screenshot({path:path.join(output,'desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.screenshot({path:path.join(output,'mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'check.json'),JSON.stringify({url,animations:checked,errors},null,2));
  console.log(JSON.stringify({passed:true,animations:checked.length}));
} finally {await browser.close();}
