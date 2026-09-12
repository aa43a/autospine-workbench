// Opt-in, external official WebGL capture of an immutable unified character bundle.
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [folderArg,outputArg,dependencies,chrome,strideArg]=process.argv.slice(2);
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
const reference=JSON.parse(files.get('/numeric-reference.json')),manifest=JSON.parse(files.get('/character-manifest.json'));
if(reference.skeleton_sha256!==inventory['skeleton.json']||manifest.authority!=='none'||manifest.production_authorized!==false)throw Error('reference_identity');
const names=Object.keys(reference.animations).sort();
if(!names.length||names.some(n=>!/^[a-zA-Z0-9_-]+$/.test(n)))throw Error('animation_name');
const packageRoot=path.resolve(dependencies,'node_modules/@esotericsoftware/spine-webgl');
const pkg=JSON.parse(await fs.readFile(path.join(packageRoot,'package.json')));
if(pkg.name!=='@esotericsoftware/spine-webgl'||pkg.version!=='4.3.13')throw Error('runtime_version');
const runtime=await fs.readFile(path.join(packageRoot,'dist/iife/spine-webgl.js'));
const harness=await fs.readFile(new URL('./character-framebuffer.js',import.meta.url));
const {chromium}=await import(pathToFileURL(path.resolve(dependencies,'node_modules/playwright-core/index.mjs')));
files.set('/runtime.js',runtime);files.set('/harness.js',harness);
files.set('/',Buffer.from('<!doctype html><canvas></canvas><script src="/runtime.js"></script><script src="/harness.js"></script>'));
const server=http.createServer((req,res)=>{
  const name=new URL(req.url,'http://localhost').pathname,raw=files.get(name);
  if(!raw){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':name.endsWith('.png')?'image/png':name.endsWith('.atlas')?'text/plain':name==='/'?'text/html':'application/json');res.end(raw);
});
async function publish(name,raw){
  const file=path.join(output,name);await fs.mkdir(path.dirname(file),{recursive:true});
  try{await fs.writeFile(file,raw,{flag:'wx'});}catch(e){if(e.code!=='EEXIST'||!Buffer.from(raw).equals(await fs.readFile(file)))throw e;}
}
let browser;
try{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.waitForFunction(()=>window.ready||window.failure,{},{timeout:120000});
  const failure=await page.evaluate(()=>window.failure);if(failure)throw Error(failure);
  const info=await page.evaluate(()=>window.captureInfo),results=[],screenshots=[];
  for(const animation of names){
    const frames=reference.animations[animation];if(!frames.length)throw Error('empty_track');
    for(let index=0;index<frames.length;index++){
      results.push(await page.evaluate(({animation,index})=>window.captureFrame(animation,index),{animation,index}));
      if(index%screenshotStride===0||index===frames.length-1){
        const raw=Buffer.from((await page.evaluate(()=>window.framePNG())).split(',')[1],'base64');
        const name=`frames/${animation}-${index}.png`;await publish(name,raw);screenshots.push({animation,index,file:name,sha256:hash(raw)});
      }
    }
    console.log(JSON.stringify({animation,frames:frames.length}));
  }
  if(errors.length)throw Error(errors.join('\n'));
  const report={schema:'autospine.character-framebuffer/v1',bundle_sha256:digest,runtime_package:pkg.name,runtime_version:pkg.version,
    runtime_sha256:hash(runtime),harness_sha256:hash(harness),tool_sha256:hash(await fs.readFile(new URL(import.meta.url))),
    browser_sha256:hash(await fs.readFile(chrome)),profile:'official-webgl-swiftshader-native-v1',info,results,screenshots,screenshot_stride:screenshotStride,
    passed:true,scope:'all_attachment_vertices_and_nonempty_unclipped_framebuffer',
    contact_status:'not_evaluated',draw_order_visual_status:'needs_review',authority:'none',production_authorized:false};
  await publish('report.json',JSON.stringify(report,null,2));
  const cards=screenshots.map(s=>`<figure><img loading="lazy" src="${s.file}" width="320"><figcaption>${s.animation} · ${s.index}</figcaption></figure>`).join('');
  await publish('index.html',`<!doctype html><meta charset="utf-8"><title>整角色 Runtime 复核</title><style>body{background:#182531;color:#eee;font:16px sans-serif}main{display:flex;flex-wrap:wrap}figure{margin:8px}img{background:repeating-conic-gradient(#34424e 0% 25%,#263540 0% 50%) 0/20px 20px}</style><h1>整角色 Runtime 复核</h1><p>官方 WebGL / SwiftShader。${results.length}帧；${info.slots}附件。仅验证位置、非空画面和裁切；接触、遮挡和整角色动作仍待复核。</p><a href="report.json">机器报告</a><main>${cards}</main>`);
  console.log(JSON.stringify({passed:true,frames:results.length,slots:info.slots,max_error_px:Math.max(...results.map(r=>r.max_error_px))}));
}finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
