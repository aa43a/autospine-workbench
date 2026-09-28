// Local delivery UI test: actual controls, Runtime, and downloaded immutable bytes.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [base,folder,deps,chrome]=process.argv.slice(2),hash=b=>createHash('sha256').update(b).digest('hex');
const url=new URL(base);assert.equal(url.hostname,'127.0.0.1');
const raw=await fs.readFile(path.join(folder,'report.json')),report=JSON.parse(raw);
assert.equal(report.selected,false);assert.equal(report.production_authorized,false);
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
  const page=await browser.newPage({viewport:{width:1250,height:1050},acceptDownloads:true}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(new URL('player.html',base).href);
  await page.waitForFunction(()=>window.characterPlayerReady||window.characterPlayerError,null,{timeout:120000});
  assert.equal(await page.evaluate(()=>window.characterPlayerError),undefined);
  assert.ok((await page.locator('#identity').innerText()).includes(report.candidate_bundle_sha256));
  await page.locator('#motion').selectOption('external-motion');
  assert.equal((await page.evaluate(()=>characterPlayerState)).duration,Math.fround(2.2));
  await page.locator('#play').click();
  await page.waitForFunction(()=>characterPlayerState.time>.1,null,{timeout:10000});
  await page.locator('#play').click();
  assert.equal((await page.evaluate(()=>characterPlayerState)).playing,false);
  for(const time of [.7,.5,.449,.617,0]){
    await page.locator('#time').evaluate((el,t)=>{el.value=String(t);el.dispatchEvent(new Event('input',{bubbles:true}));},time);
    const state=await page.evaluate(()=>characterPlayerState);assert.equal(state.time,time);assert.equal(state.playing,false);
  }
  await page.locator('#time').evaluate(el=>{el.value='.5';el.dispatchEvent(new Event('input',{bubbles:true}));});
  await page.screenshot({path:path.join(folder,'player-check.png')});
  const received=page.waitForEvent('download');await page.getByRole('link',{name:'下载诊断包'}).click();
  const download=await received;await download.saveAs(path.join(folder,'browser-download.zip'));
  const bytes=await fs.readFile(path.join(folder,'browser-download.zip'));assert.equal(hash(bytes),report.archive_sha256);
  assert.deepEqual(errors,[]);
  const result={passed:true,candidate_bundle_sha256:report.candidate_bundle_sha256,report_sha256:hash(raw),
    downloaded_sha256:hash(bytes),runtime:'actual_webgl',checks:['exact_identity','motion_selection','play_pause','forward_reverse_seek','real_download'],
    scope:'local_player_delivery_not_visual_acceptance',authority:'none',production_authorized:false};
  await fs.writeFile(path.join(folder,'browser-check.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify(result));
}finally{await browser.close();}
