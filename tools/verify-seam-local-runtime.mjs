// Opt-in official Runtime framebuffer probes; external runtime never bundled.
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [beforeRoot,afterRoot,directPath,out,dependencies,chrome,character='alice',profile='full']=process.argv.slice(2);
if(!chrome)throw Error('usage: beforeRoot afterRoot directReport output dependencies chrome');
if(!['alice','crino','lingxian'].includes(character)||!['full','native-pair'].includes(profile))throw Error('invalid_capture_profile');
const matrix=profile==='full'?{scales:[1,4],atlases:['shared','reference'],modes:['driver','follower','pair','all']}:{scales:[1],atlases:['shared'],modes:['pair','all']};
const hash=raw=>crypto.createHash('sha256').update(raw).digest('hex');
const runtime=path.join(dependencies,'node_modules/@esotericsoftware/spine-webgl/dist/iife/spine-webgl.js');
const pkg=JSON.parse(await fs.readFile(path.join(dependencies,'node_modules/@esotericsoftware/spine-webgl/package.json')));
if(pkg.version!=='4.3.13')throw Error('runtime_version');
const {chromium}=await import(pathToFileURL(path.join(dependencies,'node_modules/playwright-core/index.mjs')));
const directRaw=await fs.readFile(directPath),direct=JSON.parse(directRaw);
if(direct.schema!=='autospine.seam-direct-alpha/v1')throw Error('direct_schema');
const points=direct.relations.flatMap(r=>r.samples.map(s=>({time:s.frame/30,frame:s.frame,point:s.world_point,names:[r.driver,r.follower]})));
if(!points.length||points.length>400)throw Error('capture_scope_size');
const files=new Map(),manifests={};
for(const [variant,root] of [['before',beforeRoot],['after',afterRoot]]){
 const folder=path.resolve(root,character),raw=await fs.readFile(path.join(folder,'preview-manifest.json')),m=JSON.parse(raw);
 manifests[variant]=hash(raw);
 for(const [name,digest] of Object.entries(m.files)){
  const file=path.resolve(folder,name);if(!file.startsWith(folder+path.sep))throw Error('path_escape');
  const raw=await fs.readFile(file);if(hash(raw)!==digest)throw Error('file_hash');files.set('/'+variant+'/'+character+'/'+name,raw);
 }
 files.set('/'+variant+'/'+character+'/preview-manifest.json',raw);
}
let harness=await fs.readFile(new URL('./ownership-runtime.js',import.meta.url),'utf8');
const original="const base='/'+name+'/';";if(!harness.includes(original))throw Error('harness_base_changed');
harness=harness.replace(original,"const base='/'+new URLSearchParams(location.search).get('variant')+'/'+name+'/';");
const hook=await fs.readFile(new URL('./seam-local-framebuffer.js',import.meta.url));
const html=(await fs.readFile(new URL('./ownership-runtime.html',import.meta.url),'utf8')).replace('<script src="/ownership-runtime.js">','<script src="/local.js"></script><script src="/ownership-runtime.js">');
files.set('/',Buffer.from(html));files.set('/ownership-runtime.js',Buffer.from(harness));files.set('/local.js',hook);files.set('/runtime.js',await fs.readFile(runtime));
const server=http.createServer((req,res)=>{const name=new URL(req.url,'http://localhost').pathname,raw=files.get(name);if(!raw){res.writeHead(404);res.end();return;}
res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':name.endsWith('.png')?'image/png':name==='/'?'text/html':'application/json');res.end(raw);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const captures=[],regression=[];
try{
 for(const variant of ['before','after']){
  const page=await browser.newPage({viewport:{width:1100,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.goto('http://127.0.0.1:'+server.address().port+'/?character='+character+'&variant='+variant);
  await page.waitForFunction(()=>window.ready||window.failure,{},{timeout:60000});
  const failure=await page.evaluate(()=>window.failure);if(failure)throw Error(failure);
  const check=await page.evaluate(()=>window.verifyFrames());
  if(check.frames.length!==121||check.frames.some(f=>f.channels_over_one!==0||f.visible_pixels<=0)||
     check.max_motion_error_px>.001||check.max_page_uv_error>1e-6||check.max_setup_error_px>.001||
     check.outside_viewport_coordinates!==0||!check.animation_changed)throw Error('existing_regression_failed');
  regression.push({variant,...check});
  for(let i=0;i<points.length;i++)for(const scale of matrix.scales)for(const atlas of matrix.atlases)for(const mode of matrix.modes){
   const result=await page.evaluate(q=>window.captureLocal(q),{...points[i],scale,atlas,mode});
   const file=`${variant}-${i}-${scale}-${atlas}-${mode}.png`,raw=Buffer.from(result.image.split(',')[1],'base64');delete result.image;
   await fs.writeFile(path.join(out,file),raw);captures.push({variant,sample_index:i,...result,file,png_sha256:hash(raw)});
  }
  if(errors.length)throw Error(errors.join('\n'));await page.close();console.log(variant+': captures complete');
 }
 const report={schema:'autospine.seam-local-runtime/v2',character,profile,capture_matrix:matrix,authority:'none',production_authorized:false,status:'needs_review',
  runtime_package:pkg.name,runtime_version:pkg.version,runtime_sha256:hash(await fs.readFile(runtime)),export_target:'4.3.26',browser:await browser.version(),
  harness_sha256:hash(harness),hook_sha256:hash(hook),direct_report_sha256:hash(directRaw),bundle_manifest_sha256:manifests,
  scope:'all_recorded_points_existing_candidate_regions_only',regression,captures};
 await fs.writeFile(path.join(out,'report.json'),JSON.stringify(report,null,2));
 let view='<!doctype html><meta charset="utf-8"><style>body{font:16px system-ui;margin:30px}img{width:256px;image-rendering:pixelated;background:repeating-conic-gradient(#ccc 0% 25%,white 0% 50%) 0/16px 16px}figure{display:inline-block}</style><h1>官方 Runtime 同帧局部合成</h1><p>左原动画，右增量候选；共享 Atlas，4 倍像素密度，双附件合成。只覆盖已有候选区域，不是完整角色或生产验收。</p>';
 const viewScale=Math.max(...matrix.scales);view=view.replace('4 倍像素密度',viewScale+' 倍像素密度');
 for(let i=0;i<points.length;i++){view+=`<details${i===0?' open':''}><summary>样本 ${i} · 帧 ${points[i].frame}</summary>`;
 for(const variant of ['before','after'])view+=`<figure><figcaption>${variant}</figcaption><img loading="lazy" src="${variant}-${i}-${viewScale}-shared-pair.png"></figure>`;view+='</details>';}
 await fs.writeFile(path.join(out,'index.html'),view);console.log('captured '+captures.length+' framebuffer probes');
}finally{await browser.close();server.close();}
