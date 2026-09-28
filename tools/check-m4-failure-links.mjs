// Re-render an existing snapshot and exercise actual failed-pose links, read-only.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {supportReportHTML} from '../web/modules/motion-support-report.js';
const [input,output,deps,chrome]=process.argv.slice(2);
const raw=await fs.readFile(input),snapshot=JSON.parse(raw),base='http://127.0.0.1:8918';
await fs.mkdir(output);
const html=supportReportHTML(snapshot,base),htmlPath=path.join(output,'index.html');
await fs.writeFile(htmlPath,html,{flag:'wx'});
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,
  args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
  const context=await browser.newContext({viewport:{width:1280,height:1000}}),checked=[],errors=[];
  await context.route('**/*',route=>{assert.equal(route.request().method(),'GET');return route.continue();});
  const page=await context.newPage();await page.goto(pathToFileURL(path.resolve(htmlPath)).href);
  for(const [i,row] of snapshot.rows.entries()){
    if(!['turn','squat','boxing'].includes(row.motion))continue;
    const failure=row.review.readiness.stages.flatMap(s=>s.failures||[])
      .find(f=>typeof f.time==='number'&&Number.isFinite(f.time)&&f.time>=0);
    assert.ok(failure,`Missing recorded time for ${row.motion}/${row.character}`);
    const href=`${base}/api/motions/${row.job_id}/view/player.html?time=${encodeURIComponent(failure.time)}`;
    // Use the report's actual generated anchor, including opening its disclosure.
    const link=page.locator(`#cell-${i}`).locator(`a[href="${href}"]`).first();
    await link.evaluate(el=>{for(let p=el.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;});
    const opened=context.waitForEvent('page');await link.click();const player=await opened;
    player.on('pageerror',e=>errors.push(String(e)));
    await player.waitForLoadState();assert.equal(player.url(),href);
    await player.waitForFunction(()=>window.characterPlayerReady||window.characterPlayerError,null,{timeout:120000});
    assert.equal(await player.evaluate(()=>window.characterPlayerError),undefined);
    assert.ok((await player.locator('#identity').innerText()).includes(row.artifact_sha256));
    const state=await player.evaluate(()=>characterPlayerState);
    assert.ok(Math.abs(state.time-failure.time)<.002);assert.equal(state.playing,false);
    const screenshot=`${row.motion}-${row.character}.png`;
    await player.screenshot({path:path.join(output,screenshot)});
    checked.push({job_id:row.job_id,artifact_sha256:row.artifact_sha256,motion:row.motion,
      character:row.character,requested_time:failure.time,actual_time:state.time,screenshot});
    await player.close();console.log(`Checked ${row.motion}/${row.character}`);
  }
  assert.equal(checked.length,9);assert.deepEqual(errors,[]);
  const hash=value=>createHash('sha256').update(value).digest('hex');
  await fs.writeFile(path.join(output,'check.json'),JSON.stringify({passed:true,
    snapshot_sha256:hash(raw),html_sha256:hash(html),checked,errors,decisions_written:0,
    scope:'nine_actual_report_links_exact_candidate_time_not_quality_pass'},null,2)+'\n',{flag:'wx'});
}finally{await browser.close();}
