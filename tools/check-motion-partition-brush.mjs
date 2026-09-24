import fs from 'node:fs';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const {chromium}=createRequire(process.argv[2]+'/package.json')('playwright-core');
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.setContent('<main></main>');
 for(const name of ['mesh-brush','motion-partition-editor'])await page.addScriptTag({content:
  fs.readFileSync(`web/modules/${name}.js`,'utf8').replace(/^import .*;\r?\n/gm,'').replace('export function','function')});
 await page.evaluate(()=>{
  const image=document.createElement('canvas');image.width=image.height=100;
  window.fetch=async()=>({ok:true,json:async()=>({artifact_sha256:'exact',bones:['root'],rows:[
   {slot:'arm',mesh_sha256:'mesh',uvs:[.2,.2,.8,.2,.2,.8],triangles:[0,1,2]}]})});
  window.editor=partitionEditor(document.querySelector('main'),{job_id:'job',result:{artifact_sha256:'exact'}},
   {slot:'arm',texture:image.toDataURL()});
 });
 await page.getByRole('button',{name:'在原纹理上划分区域'}).click();
 await page.getByText('已选择 0 个三角形。',{exact:false}).waitFor();
 await page.getByLabel('区域笔刷半径').fill('2');
 const canvas=page.getByLabel('区域三角形选择画布'),bounds=await canvas.boundingBox();
 // Corner hit is far from centroid; then a single sparse move crosses the whole triangle.
 await page.mouse.click(bounds.x+21,bounds.y+21);
 assert.deepEqual(await page.evaluate(()=>editor.value().triangles),[0]);
 await page.getByRole('button',{name:'清空区域'}).click();
 await page.mouse.move(bounds.x+5,bounds.y+45);await page.mouse.down();
 await page.mouse.move(bounds.x+95,bounds.y+45,{steps:1});await page.mouse.up();
 assert.deepEqual(await page.evaluate(()=>editor.value().triangles),[0]);
 await page.getByLabel('取消区域选择').check();
 await page.mouse.click(bounds.x+21,bounds.y+21);
 assert.equal(await page.evaluate(()=>{try{editor.value();return false;}catch{return true;}}),true);
 await page.getByLabel('取消区域选择').uncheck();
 await page.mouse.click(bounds.x+95,bounds.y+95);
 assert.equal(await page.evaluate(()=>{try{editor.value();return false;}catch{return true;}}),true);
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({passed:true,corner_hit:true,sparse_stroke:true,erase:true,stroke_reset:true}));
}finally{await browser.close();}
