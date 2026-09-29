import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome,job]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  const base=`http://127.0.0.1:8918/api/production-deliveries/${job}/view/`;
  const start=performance.now();await page.goto(base+'player.html');
  await page.waitForFunction(()=>window.characterPlayerReady||window.characterPlayerError,{},{timeout:60000});
  assert.equal(await page.evaluate(()=>window.characterPlayerError),undefined);
  const load_ms=Math.round(performance.now()-start);
  const names=await page.locator('#motion option').evaluateAll(items=>items.map(i=>i.value));
  assert.equal(names.length,2);
  for(const name of names){await page.locator('#motion').selectOption(name);assert.equal(await page.evaluate(()=>characterPlayerControl.seek(.1)),true);}
  const links=[];
  for(const file of ['index.html','report.json','setup/index.html']){
    const at=performance.now(), response=await page.request.get(base+file);
    assert.equal(response.status(),200);links.push({file,ms:Math.round(performance.now()-at)});
  }
  assert.deepEqual(errors,[]);
  await page.screenshot({path:path.join(output,'player.png')});
  const report={passed:true,job,load_ms,animations:names,links,errors};
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}finally{await browser.close();}
