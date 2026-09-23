import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [base,output,dependencies]=process.argv.slice(2),fixture=JSON.parse(await fs.readFile(path.join(output,'fixture.json')));
const {chromium}=await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const prefix=base+'/api/motions/'+fixture.job;
const headers={Origin:base,'Content-Type':'application/json','X-Autospine-Intent':'pipeline-preview'};
let receipt;
try {
 const page=await browser.newPage({viewport:{width:1400,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const open=async()=>{
  await page.goto(base+'/motions.html#'+fixture.job);await page.reload();const card=page.locator('#'+fixture.job);
  await card.getByRole('button',{name:'检查可用范围与待处理项',exact:true}).click();
  await card.getByRole('button',{name:'查看变形区域与处理方案',exact:true}).click({timeout:120000});
  const editor=card.getByRole('group',{name:'当前异常的处理草稿',exact:true}).first();
  await editor.getByRole('button',{name:'加载处理草稿',exact:true}).click();
  const form=editor.getByRole('group',{name:'回交姿态素材',exact:true});await form.waitFor();return {editor,form};
 };
 let {form}=await open();
 await form.getByLabel('素材任务身份文件').setInputFiles(path.join(output,'request.json'));
 await form.getByLabel('回交姿态图片').setInputFiles(path.join(output,'source-texture.png'));
 const response=page.waitForResponse(r=>r.url()===prefix+'/material-return'&&r.request().method()==='POST');
 await form.getByRole('button',{name:'保存回交素材',exact:true}).click();
 const saved=await response;assert.equal(saved.status(),202);receipt=await saved.json();assert.equal(receipt.unchanged_source,true);assert.equal(receipt.replacement_applied,false);
 await form.getByText('已保存；图片与原纹理相同，尚未提供修改。',{exact:true}).waitFor();
 ({form}=await open());await form.getByRole('button',{name:'查看已回交版本',exact:true}).click();
 await form.getByText('当前草稿已有 1 个回交版本，均等待映射与重建。',{exact:true}).waitFor();
 const mapping=page.getByRole('group',{name:'素材区域与动作时段',exact:true}).first();
 await mapping.getByRole('button',{name:'加载回交版本和映射',exact:true}).click();
 await mapping.getByRole('button',{name:'保存区域与时段',exact:true}).waitFor();
 await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(b=>b.textContent==='保存区域与时段'&&!b.disabled));
 const pendingMesh=page.waitForResponse(r=>r.url().endsWith('/partition-mesh.json'));
 await mapping.getByRole('button',{name:'在原纹理上划分区域',exact:true}).click();
 const meshes=await (await pendingMesh).json(),mesh=meshes.rows.find(r=>r.slot===receipt.slot);
 await mapping.getByRole('button',{name:'清空区域',exact:true}).click();
 await mapping.getByText(/已选择 0 个三角形/).waitFor();
 const canvas=mapping.getByLabel('区域三角形选择画布',{exact:true});await canvas.scrollIntoViewIfNeeded();
 const bounds=await canvas.boundingBox(),tri=mesh.triangles.slice(0,3),uv=[0,1].map(k=>tri.reduce((s,v)=>s+mesh.uvs[2*v+k]/3,0));
 await page.mouse.click(bounds.x+uv[0]*bounds.width,bounds.y+uv[1]*bounds.height);
 await mapping.getByLabel('素材开始时间').fill('1');await mapping.getByLabel('素材结束时间').fill('2');
 const mapped=page.waitForResponse(r=>r.url()===prefix+'/material-mapping'&&r.request().method()==='POST');
 await mapping.getByRole('button',{name:'保存区域与时段',exact:true}).click();
 const mappingResponse=await mapped;const mappingState=await mappingResponse.json();
 await fs.writeFile(path.join(output,'mapping-response.json'),JSON.stringify({status:mappingResponse.status(),response:mappingState,request:mappingResponse.request().postDataJSON()}));
 assert.equal(mappingResponse.status(),202,JSON.stringify(mappingState));
 assert.ok(mappingState.history.at(-1).mapping.triangles.length);assert.deepEqual(mappingState.history.at(-1).mapping.interval,[1,2]);
 await mapping.getByRole('button',{name:'加载回交版本和映射',exact:true}).click();
 await mapping.getByText(/已恢复 .* 个三角形，1–2 秒/).waitFor();
 await mapping.screenshot({path:path.join(output,'mapping.png')});
 const unmapped=page.waitForResponse(r=>r.url()===prefix+'/material-mapping'&&r.request().method()==='POST');
 await mapping.getByRole('button',{name:'撤销当前素材映射',exact:true}).click();
 assert.equal((await (await unmapped).json()).history.at(-1).action,'withdraw');
 await fs.writeFile(path.join(output,'mapping.json'),JSON.stringify({passed:true,state:mappingState,withdrawn:true}));
 const layout=await form.evaluate(f=>({width:f.clientWidth,scroll:f.scrollWidth,labels:[...f.querySelectorAll('label')].map(l=>l.getBoundingClientRect().height)}));
 assert.ok(layout.scroll<=layout.width+2);assert.ok(layout.labels.every(h=>h<130),'file labels must not wrap vertically');
 await form.screenshot({path:path.join(output,'restored.png')});assert.deepEqual(errors,[]);
 await fs.writeFile(path.join(output,'browser.json'),JSON.stringify({passed:true,receipt,errors,unchanged_source_test:true}));
} finally {
 try {
 const state=await (await fetch(prefix+'/repair-draft')).json();
 // Do not overwrite a concurrent user's newer plan.
 if(state.revision!==fixture.revision)throw Error('concurrent draft change; no automatic withdrawal');
 const response=await fetch(prefix+'/repair-draft',{method:'POST',headers,body:JSON.stringify({...fixture.body,expected_revision:state.revision,action:'withdraw'})});
 assert.equal(response.status,202);
 }finally{await browser.close();}
}
const request=JSON.parse(await fs.readFile(path.join(output,'request.json'))),png_base64=(await fs.readFile(path.join(output,'source-texture.png'))).toString('base64');
const rejected=await fetch(prefix+'/material-return',{method:'POST',headers,body:JSON.stringify({request,png_base64})});
assert.equal(rejected.status,400);const reason=await rejected.json();assert.equal(reason.reason_code,'motion_material_plan_superseded');
await fs.writeFile(path.join(output,'withdrawal.json'),JSON.stringify({withdrawn:true,rejected:reason}));
console.log(JSON.stringify({passed:true,restored:true,withdrawn:true,stale_rejected:true}));
