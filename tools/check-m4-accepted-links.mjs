// Read-only browser verification of the exact accepted candidates in a saved report.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {independentAcceptedEntries} from '../web/modules/motion-support-acceptance.js';
const [snapshotPath,htmlPath,output,deps,chrome]=process.argv.slice(2);
const raw=await fs.readFile(snapshotPath),snapshot=JSON.parse(raw);
const entries=independentAcceptedEntries(snapshot);
assert.ok(entries.length>0);
await fs.mkdir(output); // Never overwrite an earlier verification.
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,
  args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),errors=[],checked=[];
  await context.route('**/*',route=>{
    assert.equal(route.request().method(),'GET','No review mutations during delivery checks');
    return route.continue();
  });
  const page=await context.newPage();
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(pathToFileURL(path.resolve(htmlPath)).href);
  for(const [i,entry] of entries.entries()){
    const expected=entry.registration_sha256?
      `/api/motions/${entry.job_id}/view/related-candidates/${entry.registration_sha256}/player.html`:
      `/api/motions/${entry.job_id}/view/player.html`;
    const row=page.locator('table tbody tr').nth(entry.cell);
    const open=row.locator(`a[href$="${expected}"]`);
    assert.equal(await open.count(),1);
    const ready=context.waitForEvent('page');await open.click();const player=await ready;
    player.on('pageerror',e=>errors.push(String(e)));
    await player.waitForLoadState();assert.equal(new URL(player.url()).pathname,expected);
    await player.waitForFunction(()=>window.characterPlayerReady||window.characterPlayerError,null,{timeout:120000});
    assert.equal(await player.evaluate(()=>window.characterPlayerError),undefined);
    assert.ok((await player.locator('#identity').innerText()).includes(entry.artifact_sha256));
    await player.locator('#motion').selectOption('external-motion');
    await player.locator('#time').evaluate(el=>{el.value=String(Number(el.max)/2);el.dispatchEvent(new Event('input',{bubbles:true}));});
    const state=await player.evaluate(()=>characterPlayerState);
    assert.ok(state.time>0);assert.equal(state.playing,false);
    await player.screenshot({path:path.join(output,`candidate-${i}.png`)});
    await player.close();
    await row.locator(`a[href="#${entry.anchor}"]`).click();
    assert.equal(await page.locator(`#${entry.anchor}`).count(),1);
    await page.waitForFunction(id=>{
      const target=document.getElementById(id);if(!target)return false;
      for(let el=target;el;el=el.parentElement)if(el.tagName==='DETAILS'&&!el.open)return false;
      return Math.abs(target.getBoundingClientRect().top)<5;
    },entry.anchor);
    checked.push({...entry,time:state.time,player_path:expected});
    console.log(`Verified accepted candidate ${i+1}/${entries.length}`);
  }
  assert.deepEqual(errors,[]);
  await page.screenshot({path:path.join(output,'report.png')});
  const hash=b=>createHash('sha256').update(b).digest('hex');
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({passed:true,
    snapshot_sha256:hash(raw),html_sha256:hash(await fs.readFile(htmlPath)),checked,
    decisions_written:0,new_runtime_capture:false,
    scope:'real_browser_navigation_identity_and_seek_not_visual_acceptance',authority:'none'},null,2)+'\n',{flag:'wx'});
}finally{await browser.close();}
