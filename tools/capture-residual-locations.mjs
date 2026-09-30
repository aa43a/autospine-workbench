// Re-capture selected same-frame differences with official Runtime world vertices.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [url,previous,bundle,dependencies,chrome,output]=process.argv.slice(2);
if(!output)throw Error('usage: url previous-report bundle dependencies chrome output');
const sha=v=>crypto.createHash('sha256').update(v).digest('hex');
const oldRaw=await fs.readFile(previous),old=JSON.parse(oldRaw);
const manifestRaw=await fs.readFile(path.join(bundle,'preview-manifest.json')),manifest=JSON.parse(manifestRaw);
if(old.schema!=='autospine.limb-residual-visibility/v1'||old.source_preview_sha256!==sha(manifestRaw))throw Error('source_identity');
const {chromium}=await import(pathToFileURL(path.join(dependencies,'node_modules/playwright-core/index.mjs')));
await fs.mkdir(output,{recursive:true});
const gpuArgs=path.basename(chrome).toLowerCase()==='chrome-headless-shell.exe'?['--in-process-gpu']:[];
const browser=await chromium.launch({executablePath:chrome,headless:true,env:{...process.env,CHROME_LOG_FILE:path.join(path.dirname(path.resolve(output)),path.basename(path.resolve(output))+'-browser-debug.log')},args:[...gpuArgs,'--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const hashes={};
async function save(name,raw){
  const dest=path.join(output,name);
  try{if(!Buffer.from(await fs.readFile(dest)).equals(Buffer.from(raw)))throw Error('output_existing_changed');}
  catch(e){if(e.code!=='ENOENT')throw e;}
  await fs.writeFile(dest,raw);hashes[name]=sha(raw);
}
try{
  const page=await browser.newPage({viewport:{width:1100,height:1100}});
  await page.goto(url);await page.waitForFunction(()=>window.residualReady||window.failure,{},{timeout:60000});
  const failure=await page.evaluate(()=>window.failure);if(failure)throw Error(failure);
  const fetchRaw=async name=>Buffer.from(await (await page.request.get(new URL(name,url).href)).body());
  if(sha(await fetchRaw('/runtime.js'))!==old.runtime_sha256)throw Error('runtime_changed');
  const camera=await page.evaluate(()=>window.residualReview.camera);
  if(JSON.stringify(camera)!==JSON.stringify(old.camera))throw Error('camera_changed');
  const rows=[];
  for(const group of old.summary){
    const samples=old.frames.map(f=>({tick:f.tick,...f.groups.find(g=>g.id===group.id)}));
    const alphaPeak=samples.reduce((a,b)=>b.pixels_exposed_by_hiding>a.pixels_exposed_by_hiding?b:a);
    for(const tick of [...new Set([group.peak_tick,alphaPeak.tick])]){
      const fresh=await page.evaluate(t=>window.residualReview.measure(t),tick/60);
      if(JSON.stringify(fresh.groups)!==JSON.stringify(old.frames.find(f=>f.tick===tick).groups))throw Error('frame_metrics_changed');
      const result=await page.evaluate(({time,id})=>window.residualReview.locate(time,id),{time:tick/60,id:group.id});
      const prefix=group.id+'-'+tick;
      for(const key of ['full_image','without_image']){
        const name=prefix+'-'+key+'.png';await save(name,Buffer.from(result[key].split(',')[1],'base64'));result[key]=name;
      }
      const sourceName='editor/images/'+group.residual[0]+'.png',raw=await fs.readFile(path.join(bundle,sourceName));
      if(sha(raw)!==manifest.files[sourceName])throw Error('residual_image_changed');
      const image=group.id+'-source.png';await save(image,raw);
      rows.push({...result,tick,residual_attachment:group.residual[0],source_image:image,
        setup_vertices_xy:manifest.regions.find(r=>r.id===group.residual[0]).setup_vertices_xy});
    }
  }
  const report={schema:'autospine.residual-location-capture/v1',source_report_sha256:sha(oldRaw),
    source_preview_sha256:sha(manifestRaw),runtime_sha256:old.runtime_sha256,runtime_version:old.runtime_version,
    hook_sha256:sha(await fetchRaw('/limb-residual-review.js')),capture_tool_sha256:sha(await fs.readFile(new URL(import.meta.url))),
    camera,rows,files:{...hashes},authority:'none',production_authorized:false};
  await save('capture.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({pairs:rows.length,targets:rows.reduce((n,r)=>n+r.targets.length,0)}));
}finally{await browser.close();}
