// Run an isolated local test renderer; never changes candidate assets or decisions.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [input,deps,chrome,output,afterSlot]=process.argv.slice(2);
const hash=b=>createHash('sha256').update(b).digest('hex');
const raw=await fs.readFile(input),fixture=JSON.parse(raw);
assert.equal(fixture.schema,'autospine.runtime-visibility-fixture/v1');
assert.equal(fixture.authority,'none');assert.equal(fixture.production_authorized,false);
if(afterSlot){assert.ok(fixture.skeleton.slots.some(s=>s.name===afterSlot));fixture.counterfactual={after_slot:afterSlot};}
const runtimePath=path.resolve(deps,'node_modules/@esotericsoftware/spine-webgl/dist/iife/spine-webgl.js');
const runtime=await fs.readFile(runtimePath);assert.equal(hash(runtime),fixture.runtime_sha256);
const helper=new URL('./runtime-material-visibility.js',import.meta.url),helperRaw=await fs.readFile(helper);
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
  page.on('console',message=>{if(message.text().startsWith('visibility trial '))console.log(message.text());});
  await page.setContent('<!doctype html><title>Local material visibility test</title>');
  await page.addScriptTag({content:runtime.toString()});await page.addScriptTag({content:helperRaw.toString()});
  const controls=await page.evaluate(async f=>{
    const checks={};
    for(const kind of ['order','image']){
      const bad={...f,rows:[{...f.rows[0]}]};
      if(kind==='order')bad.rows[0].draw_order=[...bad.rows[0].draw_order].reverse();
      else{
        const c=document.createElement('canvas');c.width=f.info.width;c.height=f.info.height;
        bad.rows[0].screenshot=c.toDataURL('image/png');
      }
      try{await window.inspectMaterialVisibility(bad);checks[kind]=false;}
      catch(e){checks[kind]=String(e).includes(kind==='order'?'visibility_order_mismatch':'visibility_prior_frame_mismatch');}
    }
    return checks;
  },{...fixture,rows:fixture.rows.slice(0,1)});
  assert.deepEqual(controls,{order:true,image:true});
  let result=null;const batchSize=fixture.whole_frame_trial?8:fixture.rows.length,batches=[];
  for(let start=0;start<fixture.rows.length;start+=batchSize){
    const batch=await page.evaluate(f=>window.inspectMaterialVisibility(f),{...fixture,rows:fixture.rows.slice(start,start+batchSize)});
    assert.deepEqual(batch.rows.map(r=>r.time),fixture.rows.slice(start,start+batchSize).map(r=>r.time));
    if(fixture.whole_frame_trial){
      const file=path.basename(output,'.json')+`-batch-${String(batches.length+1).padStart(3,'0')}.json`;
      const bytes=Buffer.from(JSON.stringify(batch));await fs.writeFile(path.join(path.dirname(output),file),bytes,{flag:'wx'});
      batches.push({file,sha256:hash(bytes),start,count:batch.rows.length});
    }
    if(!result)result=batch;else result.rows.push(...batch.rows);
    console.log('completed source frames '+result.rows.length+'/'+fixture.rows.length);
  }
  assert.deepEqual(errors,[]);
  for(const [i,row] of result.rows.entries())if(row.counterfactual){
    for(const mode of ['before','after']){
      if(!row.counterfactual[mode+'_png']){delete row.counterfactual[mode+'_png'];continue;}
      const bytes=Buffer.from(row.counterfactual[mode+'_png'].split(',')[1],'base64');
      const file=`${path.basename(output,'.json')}-trial-${i}-${mode}.png`;
      await fs.writeFile(path.join(path.dirname(output),file),bytes,{flag:'wx'});
      row.counterfactual[mode+'_image']={file,sha256:hash(bytes)};delete row.counterfactual[mode+'_png'];
    }
  }
  result.summary=result.rows.map(r=>({time:r.time,pixels:r.points.length,
    opaque_top_matches_full:r.points.filter(p=>p.opaque_top_matches_full).length,
    top_slots:Object.fromEntries([...new Set(r.points.map(p=>p.top_slot))].map(n=>[n,r.points.filter(p=>p.top_slot===n).length])),
    region_hide_changes:r.points.filter(p=>p.hide_deltas[r.region]>1).length,
    ...(r.counterfactual?{counterfactual:r.counterfactual}:{}),
    body_hide_changes:r.points.filter(p=>p.hide_deltas[r.body]>1).length,
    nearest_opaque_slots:Object.fromEntries([...new Set(r.points.map(p=>p.support.filter(s=>s.rgba[3]===255).at(-1)?.slot??'none'))].map(n=>
      [n,r.points.filter(p=>(p.support.filter(s=>s.rgba[3]===255).at(-1)?.slot??'none')===n).length]))}));
  Object.assign(result,{batches,negative_controls:controls,counterfactual:afterSlot?{after_slot:afterSlot,scope:'isolated_frame_order_trial_not_animation_candidate'}:null,
    whole_frame_trial:fixture.whole_frame_trial===true,fixture_sha256:hash(raw),runtime_sha256:hash(runtime),runtime_version:fixture.runtime_version,
    helper_sha256:hash(helperRaw),tool_sha256:hash(await fs.readFile(new URL(import.meta.url))),
    browser_sha256:hash(await fs.readFile(chrome)),bundle_sha256:fixture.bundle_sha256,
    diagnostic_sha256:fixture.diagnostic_sha256,runtime_report_sha256:fixture.runtime_report_sha256,
    skeleton_sha256:fixture.skeleton_sha256,production_authorized:false});
  await fs.writeFile(output,JSON.stringify(result,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({frames:result.rows.length,full_frame_reference:result.whole_frame_trial,output}));
}finally{await browser.close();}
