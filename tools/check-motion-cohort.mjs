// Synthetic UI review only; every mutation is intercepted before the server.
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const base='http://127.0.0.1:8918';
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const sources=['motion-'+'1'.repeat(32),'motion-'+'2'.repeat(32)];
  const targets=['motion-'+'3'.repeat(32),'motion-'+'4'.repeat(32)];
  const hash='a'.repeat(64);let changed=false,posts=0;
  await page.route('**/api/motions/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    const job=path.split('/')[3];
    if(path.endsWith('/stage-review')){
      const saved=route.request().method()==='POST';
      if(saved){posts++;assert.equal(route.request().postDataJSON().artifact_sha256,hash);}
      return route.fulfill({json:{artifact_sha256:hash,evidence_sha256:'e',revision:saved?1:0,
        readiness:{status:'needs_changes'},history:[],current_applies:saved,
        current:saved?{decision:'accepted_with_exceptions',notes:'fixture only'}:null}});
    }
    if(path.endsWith('/preview'))return route.fulfill({json:{view:'front',parents:[null,0],frames:[
      {time:0,frame:0,joints:[[0,0,0],[0,1,0]]},{time:1,frame:1,joints:[[0,0,0],[1,1,0]]}]}});
    if(path.endsWith('/rotation-status.json'))return route.fulfill({json:{artifact_sha256:hash,
      target:{records:[{bone:'upperarm_l',extra_turn_suspected:false,maximum_transfer_difference_deg:0,
        large_key_intervals:[],source_events:[{frame:2,time:.2,reason:'projection_direction_unreliable'},
          {frame:3,time:.3,reason:'projection_direction_unreliable'}]}]}}});
    if(path.endsWith('/player.html'))return route.fulfill({contentType:'text/html',body:'<p>Fixture player</p>'});
    if(sources.includes(job))return route.fulfill({json:{job_id:job,status:'succeeded',source_sha256:changed?'b'.repeat(64):hash}});
    if(targets.includes(job))return route.fulfill({json:{job_id:job,status:'succeeded',kind:'adapt',result:{artifact_sha256:hash}}});
    throw Error('unexpected fixture route '+path);
  });
  const pack={version:1,plan_sha256:hash,groups:sources.map((job_id,i)=>({job_id,label:'motion '+i,source_sha256:hash,
    targets:[{job_id:targets[i],label:'character '+i,artifact_sha256:hash}]}))};
  await page.goto(base+'/motion-cohort.html#'+encodeURIComponent(JSON.stringify(pack)));
  await page.getByText('已核对版本。查看角色动作后，可直接在本页保存阶段结论；不会自动确认。',{exact:true}).waitFor();
  assert.equal(await page.locator('iframe').count(),1);
  await page.getByRole('button',{name:'记录 / 查看阶段验收'}).click();
  await page.getByLabel('阶段验收结论').selectOption('accepted_with_exceptions');
  await page.getByLabel('验收说明').fill('fixture only');
  await page.getByRole('checkbox').check();await page.getByRole('button',{name:'保存阶段结论'}).click();
  await page.getByText('r1 · 阶段可接受，保留异常。fixture only',{exact:true}).waitFor();
  assert.equal(posts,1);
  await page.getByRole('button',{name:'在此检查旋转与绕圈'}).click();
  await page.getByText('upperarm_l · 未发现新增整圈 · 与源传递最大差 0.00°',{exact:true}).click();
  await page.getByRole('link',{name:'定位 0.200–0.300 秒（2 个源采样）'}).click();
  assert.match(await page.locator('iframe').getAttribute('src'),/player.html\?time=0.2$/);
  assert.equal(posts,1);
  await page.getByText('r1 · 阶段可接受，保留异常。fixture only',{exact:true}).waitFor();
  await page.getByRole('button',{name:'下一项'}).click();
  await page.getByRole('heading',{name:'motion 1 · character 1',exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'下一项'}).isDisabled(),true);
  assert.equal(await page.getByRole('checkbox').count(),0);
  changed=true;await page.getByRole('button',{name:'上一项'}).click();
  await page.getByText('无法打开：来源或候选身份已变化，请重新生成复核清单',{exact:true}).waitFor();
  assert.equal(await page.locator('iframe').count(),0);
  assert.equal(await page.getByRole('button',{name:'记录 / 查看阶段验收'}).count(),0);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,synthetic_posts:posts,real_decisions_written:0,checks:10}));
}finally{await browser.close();}
