import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.argv[2],parent='motion-'+'a'.repeat(32),child='motion-'+'b'.repeat(32);
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
 const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/motions',route=>route.fulfill({json:{jobs:[
  {job_id:parent,kind:'generate',name:'original',status:'canceled',view:'front',step:'generate_motion'},
  {job_id:child,kind:'generate',name:'retry',status:'interrupted',view:'front',step:'interrupted',retry_of:{job_id:parent,request_sha256:'c'.repeat(64)}}
 ],kimodo_generation:'configured',blender_available:true}}));
 await page.goto(base+'/motions.html#'+child);
 const link=page.locator('#'+child).getByRole('link',{name:'查看原生成任务（本次为独立重试）',exact:true});
 await link.waitFor();assert.equal(await link.getAttribute('href'),'/motions.html#'+parent);
 await link.click();assert.equal(new URL(page.url()).hash,'#'+parent);
 assert.equal(await page.locator('#'+parent).getByRole('link',{name:'查看原生成任务（本次为独立重试）'}).count(),0);
 assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,scope:'routed task journal navigation; no model execution'}));
}finally{await browser.close();}
