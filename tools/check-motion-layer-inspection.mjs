// Actual immutable experiment: toggle parts without changing time, camera or source.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
async function framebuffer(page){
 return page.evaluate(async()=>{
  window.characterPlayerControl.seek(window.characterPlayerState.time);
  const canvas=document.querySelector('canvas'),gl=canvas.getContext('webgl');
  const pixels=new Uint8Array(canvas.width*canvas.height*4);
  gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
  const hash=await crypto.subtle.digest('SHA-256',pixels);
  return Array.from(new Uint8Array(hash),n=>n.toString(16).padStart(2,'0')).join('');
 });
}
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE);
const evidence='0ce19ac016d1911baea39159e33b6339a5b987a0183084e1f540e364f06e2e5a';
const url=`http://127.0.0.1:8918/api/motions/motion-3954d8fe062b4a439b26a90667e97781/view/experiments/${evidence}/player.html?time=1.633333625`;
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,
  args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
 const page=await browser.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(String(e)));
 await page.route('**/api/**',route=>{
  assert.equal(route.request().method(),'GET');return route.continue();
 });
 await page.goto(url);await page.waitForFunction(()=>window.characterPlayerReady,{},{timeout:120000});
 const initial=await framebuffer(page);
 const time=await page.evaluate(()=>window.characterPlayerState.time);
 await page.getByText('部件与遮挡对照',{exact:true}).click();
 await page.locator('#inspect-a').selectOption('layer-001-r');
 await page.locator('#inspect-b').selectOption('layer-005');
 await page.locator('#inspect-mode').selectOption('isolate');
 assert.equal(await page.evaluate(()=>window.characterPlayerState.time),time);
 const isolated=await page.locator('canvas').screenshot();assert.notEqual(await framebuffer(page),initial);
 assert.deepEqual(await page.evaluate(()=>window.characterInspectionState.regions),['layer-001-r','layer-005']);
 await page.locator('#inspect-mode').selectOption('hide');
 const hidden=await framebuffer(page);assert.notEqual(hidden,initial);
 assert.equal(await page.evaluate(()=>window.characterInspectionState.hidden),true);
 await page.locator('#inspect-clear').click();
 assert.equal(await framebuffer(page),initial);
 assert.equal(await page.evaluate(()=>window.characterPlayerState.time),time);
 assert.deepEqual(errors,[]);
 const output='../tmp/m4-motion-center/layer-inspection-v1';await fs.mkdir(output,{recursive:true});
 await fs.writeFile(output+'/isolated.png',isolated);
 await fs.writeFile(output+'/report.json',JSON.stringify({passed:true,time,url,errors},null,2));
 console.log(JSON.stringify({passed:true,time,errors}));
}finally{await browser.close();}
