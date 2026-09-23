// Synthetic UI review only; every mutation is intercepted before the server.
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const base='http://127.0.0.1:8918';
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const sources=['motion-'+'1'.repeat(32),'motion-'+'2'.repeat(32)];
  const targets=['motion-'+'3'.repeat(32),'motion-'+'4'.repeat(32)];
  const alternate='motion-'+'5'.repeat(32),alternateHash='c'.repeat(64);
  const hash='a'.repeat(64);let changed=false,posts=0,staleAlternative=false;
  await page.route('**/api/motions/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    const job=path.split('/')[3];
    if(path.endsWith('/stage-review')){
      const saved=route.request().method()==='POST';
      const artifact=job===alternate?alternateHash:hash;
      if(saved){posts++;assert.equal(route.request().postDataJSON().artifact_sha256,artifact);}
      return route.fulfill({json:{artifact_sha256:artifact,evidence_sha256:job===alternate&&staleAlternative?'changed':'e',revision:saved?1:0,
        readiness:{status:'needs_changes'},history:[],current_applies:saved,
        current:saved?{decision:'accepted_with_exceptions',notes:'fixture only'}:null}});
    }
    if(path.endsWith('/preview'))return route.fulfill({json:{view:'front',parents:[null,0],frames:[
      {time:0,frame:0,joints:[[0,0,0],[0,1,0]]},{time:3,frame:1,joints:[[0,0,0],[1,1,0]]}]}});
    if(path.endsWith('/readiness.json'))return route.fulfill({json:{
      artifact_sha256:job===alternate?alternateHash:hash,skeleton_sha256:hash,status:'needs_changes',stages:[{
        stage:'遮挡',status:'needs_changes',explanation:'fixture only',href:'depth.html',
        failures:[...Array.from({length:9},(_,i)=>({time:i/10,reason:'visible_depth_straddle'})),
          {time:null,reason:'unmeasured'}]}]}});
    if(path.endsWith('/motion-depth.json'))return route.fulfill({json:{skeleton_sha256:hash,order:{failures:
      Array.from({length:30},(_,i)=>({time:i/10,pair:['arm','body'],reason_code:'visible_depth_straddle'}))}}});
    if(path.endsWith('/rotation-status.json'))return route.fulfill({json:{artifact_sha256:hash,
      target:{records:[{bone:'upperarm_l',extra_turn_suspected:false,maximum_transfer_difference_deg:0,
        large_key_intervals:[],source_events:[{frame:2,time:.2,reason:'projection_direction_unreliable'},
          {frame:3,time:.3,reason:'projection_direction_unreliable'}]}]}}});
    if(path.endsWith('/compare-targets'))return route.fulfill({json:{source_job_id:job,complete:true,recommended_job_id:alternate,
      rows:[{job_id:alternate,source_job_id:sources[0],artifact_sha256:alternateHash,evidence_sha256:'e',view:'side',status:'succeeded',stages:[]}]}});
    if(path.endsWith('/player.html'))return route.fulfill({contentType:'text/html',body:`<p>Fixture player</p><script>window.characterPlayerState={duration:3};window.characterPlayerControl={artifact:'${job===alternate?alternateHash:hash}',seek(t){window.fixtureTime=t;return true;}};</script>`});
    if(sources.includes(job))return route.fulfill({json:{job_id:job,status:'succeeded',source_sha256:changed?'b'.repeat(64):hash}});
    if(targets.includes(job))return route.fulfill({json:{job_id:job,status:'succeeded',kind:'adapt',result:{artifact_sha256:hash}}});
    if(job===alternate)return route.fulfill({json:{job_id:job,status:'succeeded',kind:'adapt',result:{artifact_sha256:alternateHash}}});
    throw Error('unexpected fixture route '+path);
  });
  const pack={version:1,plan_sha256:hash,groups:sources.map((job_id,i)=>({job_id,label:'motion '+i,source_sha256:hash,
    targets:[{job_id:targets[i],label:'character '+i,artifact_sha256:hash}]}))};
  await page.goto(base+'/motion-cohort.html#'+encodeURIComponent(JSON.stringify(pack)));
  await page.getByText('已核对版本。查看角色动作后，可直接在本页保存阶段结论；不会自动确认。',{exact:true}).waitFor()
    .catch(async error=>{console.error(JSON.stringify({errors,status:await page.locator('#status').textContent()}));throw error;});
  assert.equal(await page.locator('iframe').count(),1);
  assert.equal(await page.getByRole('link',{name:'下载此候选 Spine 包'}).getAttribute('href'),`/api/motions/${targets[0]}/download`);
  await page.getByRole('button',{name:'记录 / 查看阶段验收'}).click();
  await page.getByLabel('阶段验收结论').selectOption('accepted_with_exceptions');
  await page.getByLabel('验收说明').fill('fixture only');
  await page.getByRole('button',{name:'检查可用范围与待处理项'}).click();
  await page.getByText('异常定位（报告返回 10 条采样记录）',{exact:true}).click();
  await page.getByRole('link',{name:'异常 · 0.800 秒',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#target iframe').contentWindow.fixtureTime===.8);
  assert.equal(await page.getByLabel('验收说明').inputValue(),'fixture only');
  assert.equal(await page.getByText('未提供有效时间',{exact:false}).count(),1);
  assert.equal(posts,0);
  await page.getByRole('button',{name:'展开完整遮挡失败采样'}).click();
  await page.getByText('arm ↔ body · visible_depth_straddle · 30 条 · 0.000–2.900 秒',{exact:true}).click();
  await page.getByLabel('遮挡失败采样序号').fill('29');
  await page.getByRole('link',{name:'定位此采样',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#target iframe').contentWindow.fixtureTime===2.9);
  assert.equal(await page.getByLabel('验收说明').inputValue(),'fixture only');
  assert.equal(posts,0);
  await page.locator('#review').getByRole('checkbox').check();await page.getByRole('button',{name:'保存阶段结论'}).click();
  await page.getByText('r1 · 阶段可接受，保留异常。fixture only',{exact:true}).waitFor();
  assert.equal(posts,1);
  await page.getByRole('button',{name:'在此检查旋转与绕圈'}).click();
  await page.getByText('upperarm_l · 未发现新增整圈 · 与源传递最大差 0.00°',{exact:true}).click();
  await page.getByRole('link',{name:'定位 0.200–0.300 秒（2 个源采样）'}).click();
  await page.waitForFunction(()=>document.querySelector('#target iframe').contentWindow.fixtureTime===.2);
  assert.equal(posts,1);
  await page.getByText('r1 · 阶段可接受，保留异常。fixture only',{exact:true}).waitFor();
  await page.getByRole('button',{name:'比较该角色的已有视角候选'}).click();
  await page.getByRole('link',{name:'在当前页比较',exact:true}).click();
  const alternative=page.locator('#alternative');
  await alternative.getByRole('button',{name:'记录 / 查看阶段验收'}).click();
  assert.equal(await page.locator('iframe').count(),2);
  assert.match(await alternative.locator('iframe').getAttribute('src'),new RegExp(alternate));
  assert.equal(await alternative.getByRole('link',{name:'下载此候选 Spine 包'}).getAttribute('href'),`/api/motions/${alternate}/download`);
  await alternative.getByLabel('阶段验收结论').selectOption('accepted_with_exceptions');
  await alternative.getByLabel('验收说明').fill('fixture only');
  await alternative.getByRole('button',{name:'检查可用范围与待处理项'}).click();
  await alternative.getByText('异常定位（报告返回 10 条采样记录）',{exact:true}).click();
  await alternative.getByRole('link',{name:'异常 · 0.800 秒',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#alternative iframe').contentWindow.fixtureTime===.8);
  await page.waitForFunction(()=>document.querySelector('#target iframe').contentWindow.fixtureTime===.8);
  assert.equal(await alternative.getByLabel('验收说明').inputValue(),'fixture only');
  await alternative.getByRole('checkbox').check();
  await alternative.getByRole('button',{name:'保存阶段结论'}).click();
  await alternative.getByText('r1 · 阶段可接受，保留异常。fixture only',{exact:true}).waitFor();
  assert.equal(posts,2);
  assert.match(await page.locator('#target iframe').getAttribute('src'),new RegExp(targets[0]));
  await alternative.getByRole('button',{name:'关闭替代候选'}).click();
  staleAlternative=true;
  await page.getByRole('link',{name:'在当前页比较',exact:true}).click();
  await alternative.getByText('无法打开：来源或候选证据已变化，请重新比较',{exact:true}).waitFor();
  assert.equal(await alternative.locator('iframe').count(),0);
  assert.equal(await alternative.getByRole('link',{name:'下载此候选 Spine 包'}).count(),0);
  assert.equal(await alternative.getByRole('button',{name:'记录 / 查看阶段验收'}).count(),0);
  await page.getByRole('button',{name:'下一项'}).click();
  await page.getByRole('heading',{name:'motion 1 · character 1',exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'下一项'}).isDisabled(),true);
  assert.equal(await page.locator('#review').getByRole('checkbox').count(),0);
  assert.equal(await alternative.isHidden(),true);
  changed=true;await page.getByRole('button',{name:'上一项'}).click();
  await page.getByText('无法打开：来源或候选身份已变化，请重新生成复核清单',{exact:true}).waitFor();
  assert.equal(await page.locator('iframe').count(),0);
  assert.equal(await page.getByRole('button',{name:'记录 / 查看阶段验收'}).count(),0);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,synthetic_posts:posts,real_decisions_written:0,checks:30}));
}finally{await browser.close();}
