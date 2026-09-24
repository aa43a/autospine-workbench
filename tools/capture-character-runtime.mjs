// Opt-in, external official WebGL capture of an immutable unified character bundle.
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {readReference} from './character-reference.mjs';
import {decodeStorageReference} from './runtime-storage-input.mjs';
import {orderProbes} from './character-order-probes.mjs';
const [folderArg,outputArg,dependencies,chrome,strideArg,probeTimesArg,storageReferenceArg]=process.argv.slice(2);
if(!chrome)throw Error('usage: bundle output dependencies chrome');
const screenshotStride=strideArg===undefined?32:Number(strideArg);
if(!Number.isInteger(screenshotStride)||screenshotStride<1||screenshotStride>4096)throw Error('screenshot_stride');
const folder=path.resolve(folderArg),output=path.resolve(outputArg);
const hash=raw=>crypto.createHash('sha256').update(raw).digest('hex');
const canonical=v=>v===null||typeof v!=='object'?JSON.stringify(v):Array.isArray(v)?'['+v.map(canonical).join(',')+']':
  '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';
const inventory=JSON.parse(await fs.readFile(path.join(folder,'inventory.json')));
const digest=hash(canonical(inventory));if(digest!==path.basename(folder))throw Error('bundle_identity');
const files=new Map();let size=0;
for(const [name,sha]of Object.entries(inventory)){
  if(!/^[a-zA-Z0-9_./-]+$/.test(name)||name.split('/').some(p=>!p||p==='.'||p==='..'))throw Error('asset_path');
  const file=path.resolve(folder,name);if(!file.startsWith(folder+path.sep))throw Error('asset_path');
  const raw=await fs.readFile(file);size+=raw.length;
  if(raw.length>64*1024*1024||size>256*1024*1024||hash(raw)!==sha)throw Error('asset_inventory');
  files.set('/'+name,raw);
}
const reference=await readReference(files.get('/numeric-reference.json'),async name=>files.get('/'+name)),manifest=JSON.parse(files.get('/character-manifest.json'));
let storageEvidence=null,storageBytes=null;
if(storageReferenceArg){
  // Python bounds the uncompressed reference at 256 MiB. Large dense captures
  // can remain above 64 MiB after gzip; keep the same bounded transport budget.
  const raw=decodeStorageReference(await fs.readFile(storageReferenceArg),{inputLimit:256*1024*1024});
  const stored=JSON.parse(raw);
  if(stored.schema!=='autospine.runtime-storage-reference/v1'||stored.profile!=='spine43-linear-weighted-float32-storage-v1'||
    stored.runtime_version!=='4.3.13'||stored.skeleton_sha256!==inventory['skeleton.json']||stored.authority!=='none'||
    JSON.stringify(Object.keys(stored.animations).sort())!==JSON.stringify(Object.keys(reference.animations).sort()))throw Error('runtime_storage_reference_identity');
  let displacement=0;
  for(const [name,frames]of Object.entries(reference.animations)){
    const other=stored.animations[name];
    if(other.length!==frames.length)throw Error('runtime_storage_frame_inventory');
    for(let i=0;i<frames.length;i++){
      if(other[i].time!==frames[i].time||JSON.stringify(Object.keys(other[i].vertices).sort())!==JSON.stringify(Object.keys(frames[i].vertices).sort()))throw Error('runtime_storage_frame_inventory');
      for(const [slot,points]of Object.entries(frames[i].vertices)){
        const target=other[i].vertices[slot];
        if(target.length!==points.length||target.some(p=>!Array.isArray(p)||p.length!==2||p.some(v=>!Number.isFinite(v))))throw Error('runtime_storage_vertex_inventory');
        for(let j=0;j<points.length;j++)displacement=Math.max(displacement,Math.hypot(target[j][0]-points[j][0],target[j][1]-points[j][1]));
      }
    }
  }
  if(!Number.isFinite(stored.max_storage_displacement_px)||Math.abs(displacement-stored.max_storage_displacement_px)>1e-9||
    !/^[a-f0-9]{64}$/.test(stored.implementation_sha256))throw Error('runtime_storage_displacement_identity');
  reference.idealAnimations=reference.animations;reference.animations=stored.animations;
  storageBytes=raw;
  storageEvidence={profile:stored.profile,reference_sha256:hash(raw),implementation_sha256:stored.implementation_sha256,
    max_storage_displacement_px:stored.max_storage_displacement_px,ideal_geometry_reference_preserved:true};
}
if(files.has('/rig-setup-reference.json')){
  reference.setup=JSON.parse(files.get('/rig-setup-reference.json'));
  if(reference.setup.skeleton_sha256!==inventory['skeleton.json']||reference.setup.time!==0)throw Error('setup_reference_identity');
}
// The browser consumes the losslessly reconstructed reference after inventory verification.
files.set('/numeric-reference.json',Buffer.from(JSON.stringify(reference)));
if(reference.skeleton_sha256!==inventory['skeleton.json']||manifest.authority!=='none'||manifest.production_authorized!==false)throw Error('reference_identity');
const names=Object.keys(reference.animations).sort();
const orderCoverage=orderProbes(JSON.parse(files.get('/skeleton.json')),reference);
if(!names.length||names.some(n=>!/^[a-zA-Z0-9_-]+$/.test(n)))throw Error('animation_name');
const probeTimes=probeTimesArg===undefined?{}:JSON.parse(probeTimesArg);
if(!probeTimes||typeof probeTimes!=='object'||Array.isArray(probeTimes)||Object.keys(probeTimes).length>32)throw Error('probe_times');
for(const [name,times]of Object.entries(probeTimes)){
  if(!names.includes(name)||!Array.isArray(times)||times.length>64||times.some(t=>!Number.isFinite(t)||t<0||
    !reference.animations[name].some(f=>Math.abs(f.time-t)<1e-10)))throw Error('probe_time_missing');
}
const packageRoot=path.resolve(dependencies,'node_modules/@esotericsoftware/spine-webgl');
const pkg=JSON.parse(await fs.readFile(path.join(packageRoot,'package.json')));
if(pkg.name!=='@esotericsoftware/spine-webgl'||pkg.version!=='4.3.13')throw Error('runtime_version');
const runtime=await fs.readFile(path.join(packageRoot,'dist/iife/spine-webgl.js'));
const harness=await fs.readFile(new URL('./character-framebuffer.js',import.meta.url));
const orderReader=await fs.readFile(new URL('./character-draw-order.js',import.meta.url));
const {chromium}=await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
files.set('/runtime.js',runtime);files.set('/harness.js',harness);
files.set('/draw-order.js',orderReader);
files.set('/',Buffer.from('<!doctype html><canvas></canvas><script src="/runtime.js"></script><script src="/draw-order.js"></script><script src="/harness.js"></script>'));
const server=http.createServer((req,res)=>{
  const name=new URL(req.url,'http://localhost').pathname,raw=files.get(name);
  if(!raw){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':name.endsWith('.png')?'image/png':name.endsWith('.atlas')?'text/plain':name==='/'?'text/html':'application/json');res.end(raw);
});
async function publish(name,raw){
  const file=path.join(output,name);await fs.mkdir(path.dirname(file),{recursive:true});
  try{await fs.writeFile(file,raw,{flag:'wx'});}catch(e){if(e.code!=='EEXIST'||!Buffer.from(raw).equals(await fs.readFile(file)))throw e;}
}
let browser,page;
try{
  if(storageBytes)await publish('runtime-storage-reference.json',storageBytes);
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.waitForFunction(()=>window.ready||window.failure,{},{timeout:120000});
  const failure=await page.evaluate(()=>window.failure);if(failure)throw Error(failure);
  const info=await page.evaluate(()=>window.captureInfo),results=[],screenshots=[];
  let setupCapture=null;
  if(reference.setup){
    const result=await page.evaluate(()=>window.captureFrame(null,0));
    const raw=Buffer.from((await page.evaluate(()=>window.framePNG())).split(',')[1],'base64');
    await publish('setup-frame.png',raw);
    setupCapture={...result,file:'setup-frame.png',sha256:hash(raw)};
  }
  for(const animation of names){
    const frames=reference.animations[animation];if(!frames.length)throw Error('empty_track');
    const orderIndices=new Set((orderCoverage[animation]??[]).flatMap(key=>key.samples.map(s=>s.index)));
    for(let index=0;index<frames.length;index++){
      results.push(await page.evaluate(({animation,index})=>window.captureFrame(animation,index),{animation,index}));
      if(orderIndices.has(index)||index%screenshotStride===0||index===frames.length-1||(probeTimes[animation]??[]).some(t=>Math.abs(t-frames[index].time)<1e-10)){
        const raw=Buffer.from((await page.evaluate(()=>window.framePNG())).split(',')[1],'base64');
        const name=`frames/${animation}-${index}.png`;await publish(name,raw);screenshots.push({animation,index,file:name,sha256:hash(raw)});
      }
    }
    console.log(JSON.stringify({animation,frames:frames.length}));
  }
  if(errors.length)throw Error(errors.join('\n'));
  const report={schema:'autospine.character-framebuffer/v1',bundle_sha256:digest,runtime_package:pkg.name,runtime_version:pkg.version,
    runtime_sha256:hash(runtime),harness_sha256:hash(harness),tool_sha256:hash(await fs.readFile(new URL(import.meta.url))),
    draw_order_reader_sha256:hash(orderReader),draw_order_numeric_status:'passed',
    draw_order_switch_samples:orderCoverage,
    order_probe_selector_sha256:hash(await fs.readFile(new URL('./character-order-probes.mjs',import.meta.url))),
    reference_reader_sha256:hash(await fs.readFile(new URL('./character-reference.mjs',import.meta.url))),
    browser_sha256:hash(await fs.readFile(chrome)),profile:'official-webgl-swiftshader-native-v1',info,results,screenshots,screenshot_stride:screenshotStride,
    passed:true,scope:'all_attachment_vertices_and_nonempty_unclipped_framebuffer',
    contact_status:'not_evaluated',draw_order_visual_status:'needs_review',authority:'none',production_authorized:false,
    ...(setupCapture?{setup_capture:setupCapture}:{}),...(storageEvidence?{storage_reference:storageEvidence}:{})};
  await publish('report.json',JSON.stringify(report,null,2));
  const cards=screenshots.map(s=>`<figure><img loading="lazy" src="${s.file}" width="320"><figcaption>${s.animation} · ${s.index}</figcaption></figure>`).join('');
  await publish('index.html',`<!doctype html><meta charset="utf-8"><title>整角色 Runtime 复核</title><style>body{background:#182531;color:#eee;font:16px sans-serif}main{display:flex;flex-wrap:wrap}figure{margin:8px}img{background:repeating-conic-gradient(#34424e 0% 25%,#263540 0% 50%) 0/20px 20px}</style><h1>整角色 Runtime 复核</h1><p>官方 WebGL / SwiftShader。${results.length}帧；${info.slots}附件。仅验证位置、非空画面和裁切；接触、遮挡和整角色动作仍待复核。</p><a href="report.json">机器报告</a><main>${cards}</main>`);
  console.log(JSON.stringify({passed:true,frames:results.length,slots:info.slots,max_error_px:Math.max(...results.map(r=>r.max_error_px))}));
}catch(error){
  const detail=page?await page.evaluate(()=>window.captureFailure??null).catch(()=>null):null;
  const failure={schema:'autospine.character-capture-failure/v1',bundle_sha256:digest,
    draw_order_reader_sha256:hash(orderReader),
    runtime_version:pkg.version,runtime_sha256:hash(runtime),harness_sha256:hash(harness),
    tool_sha256:hash(await fs.readFile(new URL(import.meta.url))),
    passed:false,authority:'none',production_authorized:false,
    detail:detail??{reason_code:'capture_failed',message:String(error).slice(0,2000)}};
  await publish('failure.json',JSON.stringify(failure,null,2));
  console.error(JSON.stringify(failure));
  throw error;
}finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
