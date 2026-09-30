// Opt-in capture of newly exported sleeve assets, using external official WebGL.
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [input,contacts,output,dependencies,chrome,...remaining]=process.argv.slice(2);
const option=remaining.indexOf('--overlap'),overlapRoot=option<0?null:remaining[option+1];
const projects=option<0?remaining:remaining.slice(0,option);
if(option>=0&&(!overlapRoot||option+2!==remaining.length))throw Error('overlap_argument');
if(!chrome||!projects.length)throw Error('usage: exportRoot contactRoot output dependencies chrome projects...');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const canonical=v=>v===null||typeof v!=='object'?JSON.stringify(v):Array.isArray(v)?'['+v.map(canonical).join(',')+']':
  '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';
const profiles={
  'wide-sleeve-seven-v1':['cloth','combined_mm','combined_mp','combined_pm','combined_pp','forearm','hand'],
  'ordinary-forearm30-hand30-sine129-v1':['combined_opposed','combined_same','forearm','hand'],
  'ordinary-deform-local129-quarter513-v1':['combined_opposed','combined_same','forearm','hand']
};
function inventory(source,row){
  if(source.schema==='autospine.sleeve-export-report/v1')return {names:profiles['wide-sleeve-seven-v1'],count:257,meta:{}};
  if(source.schema!=='autospine.sleeve-export-report/v2'||!Object.hasOwn(profiles,row.motion_profile)||!(/^[a-f0-9]{64}$/).test(row.motion_source_sha256||''))throw Error('motion_profile');
  return {names:profiles[row.motion_profile],count:row.motion_profile==='ordinary-deform-local129-quarter513-v1'?513:257,meta:{motion_profile:row.motion_profile,motion_source_sha256:row.motion_source_sha256}};
}
const token=s=>{if(!/^[a-zA-Z0-9_-]+$/.test(s))throw Error('unsafe_token');return s;};
async function report(folder){
  const names=(await fs.readdir(folder)).filter(n=>/^[a-f0-9]{64}\.json$/.test(n));
  if(names.length!==1)throw Error('report_inventory');
  const raw=await fs.readFile(path.join(folder,names[0])),doc=JSON.parse(raw);
  if(hash(raw)+'.json'!==names[0])throw Error('report_digest');
  if(doc.authority!=='none'||doc.production_authorized!==false)throw Error('report_authority');
  return {doc,sha:names[0].slice(0,64)};
}
async function publish(file,raw){
  await fs.mkdir(path.dirname(file),{recursive:true});
  try{await fs.writeFile(file,raw,{flag:'wx'});}catch(e){if(e.code!=='EEXIST'||!Buffer.from(raw).equals(await fs.readFile(file)))throw e;}
}
const packageRoot=path.resolve(dependencies,'node_modules/@esotericsoftware/spine-webgl');
const pkg=JSON.parse(await fs.readFile(path.join(packageRoot,'package.json')));
if(pkg.name!=='@esotericsoftware/spine-webgl'||pkg.version!=='4.3.13')throw Error('runtime_version');
const runtime=await fs.readFile(path.join(packageRoot,'dist/iife/spine-webgl.js'));
const harness=await fs.readFile(new URL('./sleeve-framebuffer.js',import.meta.url));
const overlapHook=overlapRoot?await fs.readFile(new URL('./sleeve-overlap-framebuffer.js',import.meta.url)):null;
const tool=await fs.readFile(new URL(import.meta.url));
const {chromium}=await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
const files=new Map();
const server=http.createServer((req,res)=>{
  const name=new URL(req.url,'http://localhost').pathname,raw=files.get(name);
  if(!raw){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':name.endsWith('.png')?'image/png':name==='/'?'text/html':'application/json');res.end(raw);
});
let browser;
try{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  await fs.mkdir(output,{recursive:true});
  const gpuArgs=path.basename(chrome).toLowerCase()==='chrome-headless-shell.exe'?['--in-process-gpu']:[];
  browser=await chromium.launch({executablePath:chrome,headless:true,env:{...process.env,CHROME_LOG_FILE:path.join(path.dirname(path.resolve(output)),path.basename(path.resolve(output))+'-browser-debug.log')},args:[...gpuArgs,'--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  for(const project of projects){
    token(project);const source=await report(path.join(input,project)),contact=await report(path.join(contacts,project));
    const overlap=overlapRoot?await report(path.join(overlapRoot,project)):null;
    if(overlap&&(overlap.doc.purpose!=='sleeve_overlap_diagnostic'||overlap.doc.project_id!==project||overlap.doc.source_report_sha256!==source.sha))throw Error('overlap_source');
    const version=source.doc.schema==='autospine.sleeve-export-report/v1'?'v1':source.doc.schema==='autospine.sleeve-export-report/v2'?'v2':null;
    if(!version||source.doc.project_id!==project||
      contact.doc.schema!==`autospine.sleeve-contact-coverage/${version}`||contact.doc.project_id!==project||contact.doc.source_sha256!==source.sha)throw Error('contact_source');
    if(version==='v2'&&overlap&&overlap.doc.schema!=='autospine.sleeve-overlap/v2')throw Error('overlap_schema');
    for(const row of source.doc.records){
      if(row.status!=='candidate_exported')continue;
      const name=token(row.layer_id+'-'+row.component_id),folder=path.resolve(input,project,name);
      const matches=contact.doc.records.filter(r=>r.layer_id===row.layer_id&&r.component_id===row.component_id);
      if(matches.length!==1||canonical(matches[0].asset_sha256)!==canonical(row.files))throw Error('contact_inventory');
      const {names,meta,count}=inventory(source.doc,row),rate=(count-1)/2;
      for(const [key,value]of Object.entries(meta))if(matches[0][key]!==value)throw Error('contact_motion_source');
      files.clear();
      for(const [filename,digest] of Object.entries(row.files)){
        const file=path.resolve(folder,filename);
        if(!file.startsWith(folder+path.sep))throw Error('asset_path');
        const raw=await fs.readFile(file);if(hash(raw)!==digest)throw Error('asset_digest');files.set('/'+filename,raw);
      }
      const refRaw=await fs.readFile(path.join(folder,'numeric-reference.json')),ref=JSON.parse(refRaw);
      if(ref.skeleton_sha256!==row.files['skeleton.json'])throw Error('reference_source');
      if(version==='v2'&&JSON.parse(files.get('/skeleton.json')).skeleton.hash!==meta.motion_source_sha256)throw Error('motion_source');
      if(canonical(Object.keys(ref.animations).sort())!==canonical(names)||Object.values(ref.animations).some(f=>f.length!==count||f.some((frame,i)=>frame.time!==i/rate)))throw Error('motion_inventory');
      if(canonical(matches[0].tracks.map(t=>t.animation).sort())!==canonical(names)||matches[0].tracks.some(t=>t.frames!==count))throw Error('contact_motion_inventory');
      files.set('/numeric-reference.json',refRaw);files.set('/contact.json',Buffer.from(JSON.stringify(matches[0])));
      files.set('/runtime.js',runtime);files.set('/harness.js',harness);
      if(overlapHook)files.set('/overlap.js',overlapHook);
      files.set('/',Buffer.from('<!doctype html><canvas></canvas><script src="/runtime.js"></script>'+
        (overlapHook?'<script src="/overlap.js"></script>':'')+'<script src="/harness.js"></script>'));
      const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
      try{
        await page.goto('http://127.0.0.1:'+server.address().port+'/');
        await page.waitForFunction(()=>window.ready||window.failure,{},{timeout:60000});
        const failure=await page.evaluate(()=>window.failure);if(failure)throw Error(failure);
        const info=await page.evaluate(()=>window.captureInfo),frames=[],captures=[];
        const destination=path.resolve(output,project,name);
        for(const animation of names){
          for(let i=0;i<count;i++){
            const result=await page.evaluate(([a,i])=>window.captureFrame(a,i),[animation,i]);frames.push(result);
            if(i%((count-1)/4)===0||(result.failed_samples&&captures.length<80)){
              const raw=Buffer.from((await page.evaluate(()=>window.framePNG())).split(',')[1],'base64'),file=`${animation}-${i}.png`;
              await publish(path.join(destination,file),raw);captures.push({animation,index:i,file,sha256:hash(raw)});
            }
          }
          console.log(project,name,animation,`${count} frames`);
        }
        const overlapCaptures=[];
        if(overlap){
          const regions=overlap.doc.records.filter(r=>r.layer_id===row.layer_id&&r.component_id===row.component_id);
          if(regions.length!==1||canonical(regions[0].asset_sha256)!==canonical(row.files))throw Error('overlap_inventory');
          for(const[key,value]of Object.entries(meta))if(regions[0][key]!==value)throw Error('overlap_motion_source');
          if(canonical(regions[0].tracks.map(t=>t.animation).sort())!==canonical(names)||regions[0].tracks.some(t=>t.frames!==count))throw Error('overlap_motion_inventory');
          for(const track of regions[0].tracks){
            const peak=track.visible_peak;if(!peak)continue;
            const index=Math.round(peak.time*rate);
            if(index/rate!==peak.time||index<0||index>=count)throw Error('overlap_time');
            for(const [phase,tick] of [['setup',0],['peak',index]]){
              const result=await page.evaluate(([animation,i,pair])=>window.captureOverlap(animation,i,pair),[track.animation,tick,peak.triangles]);
              const images=[];
              for(const [mode,url] of Object.entries(result.images)){
                const raw=Buffer.from(url.split(',')[1],'base64'),file=`overlap-${track.animation}-${phase}-${mode}.png`;
                await publish(path.join(destination,file),raw);images.push({mode,file,sha256:hash(raw)});
              }
              const contextRaw=Buffer.from(result.context_image.split(',')[1],'base64'),contextFile=`overlap-${track.animation}-${phase}-context.png`;
              await publish(path.join(destination,contextFile),contextRaw);
              delete result.context_image;
              result.context={file:contextFile,sha256:hash(contextRaw)};
              result.images=images;overlapCaptures.push({phase,software_peak:peak,...result});
            }
          }
        }
        if(errors.length)throw Error(errors.join('\n'));
        const receipt={schema:`autospine.sleeve-framebuffer/${version}`,project_id:project,layer_id:row.layer_id,component_id:row.component_id,...meta,
          source_sha256:source.sha,contact_sha256:contact.sha,asset_sha256:row.files,reference_sha256:hash(refRaw),
          runtime_package:pkg.name,runtime_version:pkg.version,runtime_sha256:hash(runtime),harness_sha256:hash(harness),tool_sha256:hash(tool),
          export_target:'4.3.26',browser:await browser.version(),render_backend:'ANGLE SwiftShader WebGL',info,frames,captures,
          scope:'isolated_sleeve_native_pixel_contact_probes',status:'needs_review',authority:'none',production_authorized:false};
        if(overlap)receipt.overlap={source_sha256:overlap.sha,hook_sha256:hash(overlapHook),
          scope:'software_visible_peak_pairs_setup_and_same_frame',captures:overlapCaptures,status:'needs_review'};
        await publish(path.join(destination,hash(canonical(receipt))+'.json'),Buffer.from(canonical(receipt)));
        console.log(project,name,'complete',frames.reduce((s,f)=>s+f.failed_samples,0),'failed probes');
      }finally{await page.close();}
    }
  }
}finally{if(browser)await browser.close();server.close();}
