// Explicit opt-in official Runtime visibility inspection; no asset/decision mutation.
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [bundle,dependencies,chrome,output]=process.argv.slice(2);
if(!bundle||!dependencies||!chrome||!output)throw Error('usage: bundle dependencies chrome output');
const sha=raw=>crypto.createHash('sha256').update(raw).digest('hex');
const manifestRaw=await fs.readFile(path.join(bundle,'preview-manifest.json')),manifest=JSON.parse(manifestRaw);
if(manifest.schema!=='autospine.wing-limb-preview/v1'||manifest.production_authorized!==false)throw Error('source_profile');
const character=path.basename(path.resolve(bundle));
if(!['alice','lingxian','crino'].includes(character))throw Error('character_invalid');
const runtime=path.join(dependencies,'node_modules/@esotericsoftware/spine-webgl/dist/iife/spine-webgl.js');
const pkg=JSON.parse(await fs.readFile(path.join(dependencies,'node_modules/@esotericsoftware/spine-webgl/package.json')));
if(pkg.name!=='@esotericsoftware/spine-webgl'||pkg.version!=='4.3.13')throw Error('runtime_version');
const {chromium}=await import(pathToFileURL(path.join(dependencies,'node_modules/playwright-core/index.mjs')));
const files=new Map([['/runtime.js',runtime],['/'+character+'/preview-manifest.json',path.join(bundle,'preview-manifest.json')]]);
const toolHashes={};
for(const name of ['ownership-runtime.js','limb-residual-metrics.js','limb-residual-review.js']){
  const file=new URL('./'+name,import.meta.url);files.set('/'+name,file);toolHashes[name]=sha(await fs.readFile(file));
}
const sourceFiles=[];
for(const [name,digest] of Object.entries(manifest.files)){
  const file=path.resolve(bundle,name);
  if(!file.startsWith(path.resolve(bundle)+path.sep)||sha(await fs.readFile(file))!==digest)throw Error('source_file_changed');
  files.set('/'+character+'/'+name,file);sourceFiles.push([file,digest]);
}
const originalHtml=await fs.readFile(new URL('./ownership-runtime.html',import.meta.url),'utf8');
toolHashes['ownership-runtime.html']=sha(originalHtml);
const html=originalHtml.replace('<script src="/ownership-runtime.js">','<script src="/limb-residual-metrics.js"></script><script src="/limb-residual-review.js"></script><script src="/ownership-runtime.js">');
const server=http.createServer(async(req,res)=>{
  try{
    const url=new URL(req.url,'http://localhost');
    if(url.pathname==='/'){res.setHeader('Content-Type','text/html');res.end(html);return;}
    const file=files.get(url.pathname);if(!file){res.writeHead(404);res.end();return;}
    res.setHeader('Content-Type',({'.js':'text/javascript','.png':'image/png','.html':'text/html','.json':'application/json'})[path.extname(String(file))]||'text/plain');
    res.end(await fs.readFile(file));
  }catch{res.writeHead(500);res.end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const url='http://127.0.0.1:'+server.address().port+'/?character='+character;
console.log('Residual review: '+url);
await fs.mkdir(output,{recursive:true});
const outputHashes={};
async function save(name,raw){
  const dest=path.join(output,name);
  try{if(!Buffer.from(await fs.readFile(dest)).equals(Buffer.from(raw)))throw Error('output_existing_changed');}
  catch(e){if(e.code!=='ENOENT')throw e;}
  await fs.writeFile(dest,raw);outputHashes[name]=sha(raw);
}
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
let passed=false;
try{
  const page=await browser.newPage({viewport:{width:1100,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(url);await page.waitForFunction(()=>window.residualReady||window.failure,{},{timeout:60000});
  const failure=await page.evaluate(()=>window.failure);if(failure)throw Error(failure);
  const groups=await page.evaluate(()=>window.residualReview.groups),camera=await page.evaluate(()=>window.residualReview.camera);
  const checks=await page.evaluate(()=>{
    let invalid=false;try{window.residualReview.render(0,'invalid');}catch{invalid=true;}
    return {unknown_mode_rejected:invalid,restored_same_frame:[0,.5,1,1.5,2].every(t=>window.residualReview.restoreCheck(t))};
  });
  if(!checks.unknown_mode_rejected||!checks.restored_same_frame)throw Error('review_restore_failed');
  const frames=[];
  for(let tick=0;tick<=120;tick++){
    frames.push({tick,...await page.evaluate(t=>window.residualReview.measure(t),tick/60)});
    if(tick%30===0)console.log('Measured '+tick+'/120');
  }
  const summary=groups.map(g=>{
    const samples=frames.map(f=>({tick:f.tick,...f.groups.find(r=>r.id===g.id)}));
    const peak=samples.reduce((a,b)=>b.changed_pixels>a.changed_pixels?b:a);
    return {...g,visible_contribution_frames:samples.filter(s=>s.changed_pixels>0).length,
      peak_changed_pixels:peak.changed_pixels,peak_tick:peak.tick,
      peak_any_channel_changed_pixels:Math.max(...samples.map(s=>s.any_channel_changed_pixels)),
      peak_exposed_by_hiding:Math.max(...samples.map(s=>s.pixels_exposed_by_hiding))};
  });
  const ticks=[...new Set([0,30,60,90,120,...summary.map(r=>r.peak_tick)])].sort((a,b)=>a-b);
  const shots=[];
  for(const tick of ticks)for(const mode of ['full','without-all','residual-only']){
    const data=await page.evaluate(({t,m})=>window.residualReview.render(t,m),{t:tick/60,m:mode});
    const name=`frame-${tick}-${mode}.png`;await save(name,Buffer.from(data.split(',')[1],'base64'));shots.push({tick,mode,file:name});
  }
  for(const [file,digest] of sourceFiles)if(sha(await fs.readFile(file))!==digest)throw Error('source_changed_during_review');
  if(errors.length)throw Error(errors.join('\n'));
  const report={schema:'autospine.limb-residual-visibility/v1',character_id:manifest.character_id,source_preview_sha256:sha(manifestRaw),
    runtime_package:pkg.name,runtime_version:pkg.version,runtime_sha256:sha(await fs.readFile(runtime)),
    tool_hashes:toolHashes,browser:await browser.version(),camera,thresholds:{alpha:8,channel_delta:1},
    frames,summary,shots,checks,source_files_unchanged:true,
    interpretation:'visibility_contribution_only_not_crack_or_ownership_adoption',authority:'none',production_authorized:false,files:{...outputHashes}};
  await save('report.json',JSON.stringify(report,null,2)+'\n');
  const esc=x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
  const rows=summary.map(g=>`<tr><td>${esc(g.name)}</td><td>${g.source_pixels}</td><td>${g.visible_contribution_frames}/121</td><td>${g.peak_changed_pixels}（${g.peak_tick}/60 秒）</td><td>${g.peak_exposed_by_hiding}</td></tr>`).join('');
  const gallery=ticks.map(t=>`<h2>${t}/60 秒</h2><div class="grid">${shots.filter(s=>s.tick===t).map(s=>`<figure><a href="${s.file}"><img src="${s.file}"></a><figcaption>${esc({'full':'完整合成','without-all':'临时隐藏残余','residual-only':'仅残余'}[s.mode])}</figcaption></figure>`).join('')}</div>`).join('');
  await save('index.html',`<!doctype html><meta charset="utf-8"><title>四肢残余同帧复核</title><style>body{font:17px/1.6 system-ui;margin:32px;background:#eef1f5;color:#243448}table{border-collapse:collapse}td,th{padding:12px;border:1px solid #bbb}.grid{display:grid;grid-template-columns:repeat(3,1fr)}figure{margin:8px}img{width:100%;background:white}h2{margin-top:40px}</style><h1>四肢残余同帧显隐复核</h1><p>原候选资产未修改。颜色变化和“隐藏后透明”只说明画面对残余有依赖，不是原动画裂缝判定，更不是删除建议。数值来自当前相机下的 framebuffer 像素，不等于源纹理像素。</p><p><a href="report.json">逐帧结果</a></p><table><tr><th>源层</th><th>源残余像素</th><th>有可见贡献帧数</th><th>峰值变化像素</th><th>隐藏后透明峰值</th></tr>${rows}</table>${gallery}`);
  files.set('/summary',path.join(output,'index.html'));
  for(const name of Object.keys(outputHashes))files.set('/'+name,path.join(output,name));
  console.log(JSON.stringify(summary));console.log('Report: '+path.resolve(output,'index.html'));passed=true;
}finally{await browser.close();if(process.env.KEEP_PREVIEW!=='1'||!passed)server.close();}
