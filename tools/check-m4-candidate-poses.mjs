// Capture exact candidate poses for review; never write acceptance or change assets.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const [auditPath,output,deps,chrome]=process.argv.slice(2);
const raw=await fs.readFile(auditPath),audit=JSON.parse(raw);
assert.ok(audit.rows?.length);
await fs.mkdir(output); // Do not overwrite earlier evidence.
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,
  args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
try{
  const context=await browser.newContext({viewport:{width:1280,height:1000}});
  await context.route('**/*',route=>{
    assert.equal(route.request().method(),'GET');return route.continue();
  });
  const rows=[],errors=[];
  for(const [i,row] of audit.rows.entries()){
    assert.equal(new URL(row.player_url).hostname,'127.0.0.1');
    const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
    await page.goto(row.player_url);
    await page.waitForFunction(()=>window.characterPlayerReady||window.characterPlayerError,null,{timeout:120000});
    assert.equal(await page.evaluate(()=>window.characterPlayerError),undefined);
    assert.ok((await page.locator('#identity').innerText()).includes(row.artifact_sha256));
    await page.locator('#motion').selectOption('external-motion');
    const duration=await page.evaluate(()=>characterPlayerState.duration),poses=[];
    for(const fraction of [0,.25,.5,.75,1]){
      const time=duration*fraction;
      await page.locator('#time').evaluate((el,t)=>{el.value=String(t);el.dispatchEvent(new Event('input',{bubbles:true}));},time);
      const state=await page.evaluate(()=>characterPlayerState);
      assert.ok(Math.abs(state.time-time)<.002);assert.equal(state.playing,false);
      const file=`candidate-${i}-pose-${poses.length}.png`;
      await page.locator('canvas').screenshot({path:path.join(output,file)});
      poses.push({time:state.time,file});
    }
    rows.push({character:row.character,job_id:row.job_id,artifact_sha256:row.artifact_sha256,
      player_url:row.player_url,readiness_status:row.readiness_status,poses});
    await page.close();
  }
  assert.deepEqual(errors,[]);
  const report={passed:true,audit_sha256:createHash('sha256').update(raw).digest('hex'),rows,
    decisions_written:0,scope:'five_exact_runtime_poses_not_full_timeline_quality_check'};
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
  await fs.writeFile(path.join(output,'index.html'),`<!doctype html><meta charset="utf-8"><title>Reach 姿态对照</title>
<style>body{background:#111d29;color:#eee;font:16px sans-serif;padding:24px}a{color:#69caff}.poses{display:flex;overflow:auto;gap:12px}figure{margin:0;min-width:320px}img{width:320px}code{word-break:break-all}</style>
<h1>Reach 姿态对照</h1><p>五个同版本 Runtime 时刻用于定位。遮挡异常保留；不代表完整动画或人工验收通过。</p>
${rows.map(row=>`<h2>${escape(row.character)}</h2><p><a href="${escape(row.player_url)}">打开可播放候选与时间轴</a> · ${escape(row.readiness_status)}</p><code>${escape(row.artifact_sha256)}</code><div class="poses">${row.poses.map(p=>`<figure><img src="${p.file}"><figcaption>${p.time.toFixed(3)} 秒</figcaption></figure>`).join('')}</div>`).join('')}`,{flag:'wx'});
  console.log(JSON.stringify({passed:true,candidates:rows.length,poses:rows.reduce((n,r)=>n+r.poses.length,0)}));
}finally{await browser.close();}
