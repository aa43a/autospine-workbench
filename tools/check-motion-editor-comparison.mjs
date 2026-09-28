// Compare editor framebuffer to the actual exported candidate's standalone player.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [output,deps,chrome,id]=process.argv.slice(2);await fs.mkdir(output);
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
  const editor=await browser.newPage({viewport:{width:1440,height:1100}}),player=await browser.newPage(),errors=[];
  for(const page of [editor,player])page.on('pageerror',e=>errors.push(String(e)));
  await editor.goto(`http://127.0.0.1:8918/motion-editor.html#${id}`);
  const job=await (await editor.request.get(`http://127.0.0.1:8918/api/motions/${id}`)).json();
  await editor.getByText('在编辑区对照导出结果',{exact:true}).click();
  try{await editor.waitForFunction(()=>!document.querySelector('#restore-result').disabled,{},{timeout:60000});}
  catch(e){await fs.writeFile(path.join(output,'failure.json'),JSON.stringify({errors,status:await editor.locator('#result-status').innerText()},null,2));throw e;}
  await editor.click('#restore-result');
  await editor.waitForFunction(()=>window.motionEditorResultState?.status==='matching',{},{timeout:60000});
  if(job.result.projection.sampling_profile==='camera-world-projected-adaptive-v2'){
    assert.equal(await editor.locator('#sampling-version').inputValue(),job.result.projection.sampling_profile);
    await editor.click('#save-draft');await editor.selectOption('#sampling-version','camera-world-linear-adaptive-v1');
    await editor.click('#restore-draft');
    await editor.waitForFunction(()=>document.querySelector('#sampling-version').value==='camera-world-projected-adaptive-v2');
    await editor.waitForFunction(()=>window.motionEditorResultState?.status==='matching');
  }
  assert.equal(await editor.evaluate(()=>{
    const a=document.querySelector('#character-canvas'),b=document.querySelector('#result-canvas');
    return a.width===b.width&&a.height===b.height;
  }),true);
  await player.goto(`http://127.0.0.1:8918/api/motions/${id}/view/player.html`);
  await player.waitForFunction(()=>window.characterPlayerReady,{},{timeout:60000});
  async function capture(page,time,isEditor){return page.evaluate(async({time,isEditor})=>{
    if(isEditor){const el=document.querySelector('#time');el.value=time;el.dispatchEvent(new Event('input'));}
    else if(!window.characterPlayerControl.seek(time))throw Error('seek failed');
    const canvas=document.querySelector(isEditor?'#result-canvas':'canvas'),gl=canvas.getContext('webgl');
    const pixels=new Uint8Array(canvas.width*canvas.height*4);gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
    let opaque=0;for(let i=3;i<pixels.length;i+=4)if(pixels[i])opaque++;
    return {width:canvas.width,height:canvas.height,opaque,sha:Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',pixels)),n=>n.toString(16).padStart(2,'0')).join('')};
  },{time,isEditor});}
  const duration=await editor.locator('#time').evaluate(el=>Number(el.max));
  assert.ok(Number.isFinite(duration)&&duration>0);
  const revisit=duration*.1,records=[];
  for(const time of [0,revisit,duration*.492,duration*.997,revisit]){
    const a=await capture(editor,time,true),b=await capture(player,time,false);
    assert.ok(a.opaque>1000);assert.deepEqual(a,b);records.push({time,...a});
  }
  await editor.fill('#yaw-value','45');await editor.locator('#yaw-value').dispatchEvent('change');
  await editor.waitForFunction(()=>window.motionEditorResultState?.status==='draft_changed');
  let accidentalSubmissions=0;editor.on('request',r=>{if(r.url().endsWith('/adapt')&&r.method()==='POST')accidentalSubmissions++;});
  if(job.result.projection.keys?.length>1){await editor.click('#build');await editor.waitForFunction(()=>document.querySelector('#build-status').textContent.includes('尚未写入轨道'));}
  assert.equal(accidentalSubmissions,0);
  assert.equal((await capture(editor,revisit,true)).sha,records[1].sha);
  await editor.locator('.canvases').screenshot({path:path.join(output,'comparison.png')});
  await editor.selectOption('#project','');
  await editor.waitForFunction(()=>window.motionEditorResultState?.status==='different_source');
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({passed:true,job_id:id,records,stale_and_mismatch_checked:true,errors},null,2));
}finally{await browser.close();}
