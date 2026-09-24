import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [folder,output,dependencies]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try{
 const page=await browser.newPage({viewport:{width:1250,height:1000}}),errors=[];let submitted=null;
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('http://pose-editor.test/**',async route=>{
  const name=new URL(route.request().url()).pathname.slice(1)||'index.html';
  if(name==='api/motions/test/pose-geometry-execute'){
   submitted=route.request().postDataJSON();assert.equal(route.request().headers()['x-autospine-intent'],'pipeline-preview');
   return route.fulfill({json:{job_id:'motion-test'}});
  }
  if(!/^[a-zA-Z0-9.-]+$/.test(name))return route.abort();
  if(name==='source-comparison.json'){
   const config=JSON.parse(await fs.readFile(path.join(folder,'editor-config.json')));
   return route.fulfill({json:{artifact_sha256:config.artifact,source_start:2,duration:config.request.interval[1],
    preview:{parents:[null,0],view:'front',frames:Array.from({length:101},(_,i)=>({time:2+i*.1,frame:i,joints:[[0,0,0],[i*.01,1,i*.02]]}))}}});
  }
  const type=name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':name.endsWith('.json')?'application/json':'text/html';
  const source={'index.html':'pose-geometry-editor.html','editor.js':'pose-geometry-editor.js','editor.css':'pose-geometry-editor.css',
   'pose-source.js':'modules/pose-source.js','motion-source-player.js':'modules/motion-source-player.js'}[name];
  let body=await fs.readFile(source?path.join('web',source):path.join(folder,name));
  if(name==='editor-config.json')body=Buffer.from(JSON.stringify({...JSON.parse(body),source_comparison_url:'source-comparison.json',execute_url:'/api/motions/test/pose-geometry-execute'}));
  await route.fulfill({body,contentType:type});
 });
 await page.goto('http://pose-editor.test/?time=0.7');
 await page.waitForFunction(()=>window.poseGeometryEditorReady||window.poseGeometryEditorError,{},{timeout:60000});
 assert.equal(await page.evaluate(()=>window.poseGeometryEditorError),undefined);
 assert.equal(await page.evaluate(()=>window.poseGeometryEditorState.time),.7);
 await page.waitForFunction(()=>document.getElementById('source-position').dataset.requestedTime==='2.7');
 await page.locator('#source-view').selectOption('side');
 assert.equal(await page.locator('#source-position').getAttribute('data-requested-time'),'2.7');
 const seek=async t=>page.locator('#time').evaluate((e,t)=>{e.value=t;e.dispatchEvent(new Event('input'));},t);
 const drag=async(index,dx,dy)=>{
  const xy=await page.evaluate(index=>{const canvas=document.querySelector('canvas'),r=canvas.getBoundingClientRect();
   const [x,y]=window.poseGeometryEditorState.points[index],i=window.poseGeometryEditorState.view;
   return [r.left+(x-i.left)/i.width*r.width,r.top+(i.bottom+i.height-y)/i.height*r.height];},index);
  await page.mouse.move(...xy);await page.mouse.down();await page.mouse.move(xy[0]+dx,xy[1]+dy,{steps:4});await page.mouse.up();
 };
 const config=JSON.parse(await fs.readFile(path.join(folder,'editor-config.json'),'utf8'));
 const vertex=config.request.vertices[10];
 await seek(1);
 assert.equal(await page.locator('#source-position').getAttribute('data-requested-time'),'3');
 await page.locator('#focus').click();
 assert.ok(await page.evaluate(()=>window.poseGeometryEditorState.view.height<1000));
 const before=await page.evaluate(v=>window.poseGeometryEditorState.points[v],vertex);
 await drag(vertex,8,-4);
 assert.equal(await page.evaluate(()=>window.poseGeometryEditorState.poses.length),1);
 const after=await page.evaluate(v=>window.poseGeometryEditorState.points[v],vertex);
 assert.ok(Math.hypot(after[0]-before[0],after[1]-before[1])>1);
 await seek(.6);await seek(1);
 assert.deepEqual(await page.evaluate(v=>window.poseGeometryEditorState.points[v],vertex),after);
 await page.locator('#preview').uncheck();
 assert.deepEqual(await page.evaluate(v=>window.poseGeometryEditorState.points[v],vertex),before);
 await page.locator('#preview').check();
 await seek(1.2);await drag(vertex,-5,2);
 assert.equal(await page.evaluate(()=>window.poseGeometryEditorState.poses.length),2);
 await page.locator('#undo').click();
 assert.equal(await page.evaluate(()=>window.poseGeometryEditorState.poses.length),1);
 await drag(vertex,-5,2);
 await fs.mkdir(output,{recursive:true});
 const pending=page.waitForEvent('download');await page.locator('#download').click();
 await (await pending).saveAs(path.join(output,'request.json'));
  await page.reload();await page.waitForFunction(()=>window.poseGeometryEditorReady,{},{timeout:60000});
  assert.equal(await page.evaluate(()=>window.poseGeometryEditorState.poses.length),2);
 const invalid={...JSON.parse(await fs.readFile(path.join(output,'request.json'),'utf8')),document_sha256:'0'.repeat(64)};
 await page.locator('#import').setInputFiles({name:'wrong-version.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(invalid))});
 await page.waitForFunction(()=>document.getElementById('status').textContent.includes('版本不匹配'));
 assert.equal(await page.evaluate(()=>window.poseGeometryEditorState.poses.length),2);
 await page.locator('#import').setInputFiles(path.join(output,'request.json'));
 await page.waitForFunction(()=>document.getElementById('status').textContent.includes('已保存 2'));
 await seek(.5);await page.locator('#play').click();
 await page.waitForFunction(()=>window.poseGeometryEditorState.time>.6);
 await page.locator('#play').click();
 await seek(1.2);
 await page.locator('#build').click();
 await page.waitForFunction(()=>document.getElementById('build-status').textContent.includes('修改已封存'));
 assert.equal(submitted.artifact_sha256,config.artifact);
 assert.deepEqual(submitted.pose_geometry,JSON.parse(await fs.readFile(path.join(output,'request.json'),'utf8')));
 await page.locator('#focus').click();
 const state=await page.evaluate(()=>window.poseGeometryEditorState);
  await fs.writeFile(path.join(output,'preview.json'),JSON.stringify(state));
 const interpolation=[];
 for(const t of [.6,1,1.1,1.2,1.6]){await seek(t);interpolation.push(await page.evaluate(()=>window.poseGeometryEditorState));}
 await fs.writeFile(path.join(output,'interpolation.json'),JSON.stringify(interpolation));
 await seek(1.2);
 await page.screenshot({path:path.join(output,'editor.png')});
 await page.locator('#keys').selectOption('1');await page.locator('#remove').click();
 assert.equal(await page.evaluate(()=>window.poseGeometryEditorState.poses.length),1);
 assert.deepEqual(errors,[]);
 await page.route('http://pose-editor.test/source-comparison.json',route=>route.fulfill({json:{artifact_sha256:'wrong'}}));
 await page.reload();
 await page.waitForFunction(()=>document.getElementById('source-error').textContent.includes('版本不匹配'));
 assert.equal(await page.evaluate(()=>window.poseGeometryEditorReady),true);
 assert.equal(await page.locator('#source-reference').isVisible(),false);
 await fs.writeFile(path.join(output,'check.json'),JSON.stringify({passed:true,artifact:config.artifact,vertex,errors,
  scope:'drag_seek_source_toggle_undo_export_reload_remove_not_quality_acceptance'},null,2));
 console.log(JSON.stringify({passed:true,vertex,artifact:config.artifact}));
}finally{await browser.close();}
