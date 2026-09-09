// Verify a published project job with an external official Runtime, without granting authority.
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';

const [base,project,job,dependencies,chrome,output] = process.argv.slice(2);
if (!output) throw Error('usage: baseURL project_id job_id dependencies chrome outputDir');
if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(project) || !/^job-[a-f0-9]{32}$/.test(job)) throw Error('identity_invalid');
const origin=new URL(base);
if (origin.protocol!=='http:' || !['127.0.0.1','localhost','[::1]'].includes(origin.hostname) || origin.username || origin.password) throw Error('local_base_required');
const endpoint=new URL(`/api/projects/${encodeURIComponent(project)}/automation/animated/jobs/${job}`,origin).href;
const sha=raw=>crypto.createHash('sha256').update(raw).digest('hex');
async function get(url) {const r=await fetch(url,{redirect:'error'}); if(!r.ok) throw Error(`fetch_failed_${r.status}`); return Buffer.from(await r.arrayBuffer());}
function safe(name) {
  if (!/^[A-Za-z0-9_./-]{1,240}$/.test(name) || name.startsWith('/') || name.split('/').some(p=>['','.','..'].includes(p)) || !/\.(json|atlas|png)$/.test(name)) throw Error('manifest_path_invalid');
  return name;
}
const jobRaw=await get(endpoint), receipt=JSON.parse(jobRaw);
if (receipt.schema!=='autospine.animated-web-job/v1' || receipt.job_id!==job || receipt.project_id!==project || receipt.authority!=='none'
    || !['needs_review','succeeded'].includes(receipt.status) || receipt.run?.preview_available!==true) throw Error('preview_not_available');
const manifestRaw=await get(endpoint+'/files/preview-manifest.json'), manifest=JSON.parse(manifestRaw);
if (manifest.schema!=='autospine.workbench-animated-preview/v1' || manifest.authority!=='none' || manifest.production_authorized!==false) throw Error('manifest_invalid');
if (manifest.animation!==receipt.run.clip || JSON.stringify(manifest.source_addresses)!==JSON.stringify(receipt.run.source_addresses)) throw Error('run_manifest_mismatch');
const packageRoot=path.join(dependencies,'node_modules/@esotericsoftware/spine-webgl');
const packageRaw=await fs.readFile(path.join(packageRoot,'package.json')), runtimePackage=JSON.parse(packageRaw);
if (runtimePackage.name!=='@esotericsoftware/spine-webgl' || runtimePackage.version!=='4.3.13') throw Error('official_runtime_version_mismatch');
const runtimeRaw=await fs.readFile(path.join(packageRoot,'dist/iife/spine-webgl.js'));
const harnessRaw=await fs.readFile(new URL('./animated-workbench-runtime.js',import.meta.url));
const files=new Map([['/runtime.js',runtimeRaw],['/probe.js',harnessRaw],['/assets/preview-manifest.json',manifestRaw],
  ['/',Buffer.from('<!doctype html><meta charset="utf-8"><title>Official Runtime candidate verification</title><canvas width="900" height="900"></canvas><script src="/runtime.js"></script><script src="/probe.js"></script>')]]);
const entries=Object.entries(manifest.files);
if (!entries.length || entries.length>1024) throw Error('manifest_files_invalid');
// The verified endpoint emits ZIP_STORED; one request avoids re-reading the entire
// addressed bundle and source closure for every individual image.
console.log('Downloading verified preview ZIP');
const archive=await get(endpoint+'/download'), extracted=new Map();
if (archive.length<22 || archive.length>300*1024*1024 || archive.readUInt32LE(archive.length-22)!==0x06054b50) throw Error('zip_invalid');
let offset=0;
while (offset+30<=archive.length && archive.readUInt32LE(offset)===0x04034b50) {
  if (archive.readUInt16LE(offset+8)!==0 || (archive.readUInt16LE(offset+6)&9)) throw Error('zip_format_unsupported');
  const size=archive.readUInt32LE(offset+18), expanded=archive.readUInt32LE(offset+22);
  const length=archive.readUInt16LE(offset+26), extra=archive.readUInt16LE(offset+28), start=offset+30+length+extra;
  if (size!==expanded || start+size>archive.length) throw Error('zip_entry_invalid');
  const name=safe(archive.subarray(offset+30,offset+30+length).toString('utf8'));
  if (extracted.has(name) || extracted.size>=1024) throw Error('zip_entry_duplicate');
  extracted.set(name,archive.subarray(start,start+size)); offset=start+size;
}
if (offset!==archive.readUInt32LE(archive.length-6) || extracted.size!==archive.readUInt16LE(archive.length-12)
    || extracted.size!==entries.length+1 || sha(extracted.get('preview-manifest.json')||Buffer.alloc(0))!==sha(manifestRaw)) throw Error('zip_manifest_mismatch');
for (const [name,digest] of entries) {
  safe(name); if(!/^[a-f0-9]{64}$/.test(digest)) throw Error('manifest_digest_invalid');
  const raw=extracted.get(name); if(!raw || sha(raw)!==digest) throw Error('published_file_changed');
  files.set('/assets/'+name,raw);
}
console.log('Verified ZIP assets: '+entries.length);
for (const name of ['skeleton.json','skeleton.atlas','playback.json']) if (!files.has('/assets/'+name)) throw Error('required_file_missing');
const server=http.createServer((request,response)=>{
  const name=new URL(request.url,'http://127.0.0.1').pathname,raw=files.get(name);
  if(!raw){response.writeHead(404);response.end();return;}
  response.setHeader('Content-Type',name==='/'?'text/html':name.endsWith('.js')?'text/javascript':name.endsWith('.png')?'image/png':name.endsWith('.json')?'application/json':'text/plain');
  response.end(raw);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try {
  const {chromium}=await import(pathToFileURL(path.join(dependencies,'node_modules/playwright-core/index.mjs')));
  browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  const page=await browser.newPage({viewport:{width:1000,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  console.log('Loading official Runtime');
  await page.waitForFunction(()=>window.ready||window.failure,{},{timeout:60000});
  const failure=await page.evaluate(()=>window.failure); if(failure) throw Error(failure);
  const result=await page.evaluate(()=>window.verifyAnimated()); result.passed=result.passed&&!errors.length;
  await fs.mkdir(output,{recursive:true});
  const images={};
  for (const [name,time] of [['setup.png',0],['bend.png',.5]]) {
    await page.evaluate(t=>window.renderAnimatedAt(t),time);
    const raw=await page.locator('canvas').screenshot(); images[name]=sha(raw); await fs.writeFile(path.join(output,name),raw);
  }
  // Reject a changing job/manifest while the frame probe was executing.
  if (sha(await get(endpoint))!==sha(jobRaw) || sha(await get(endpoint+'/files/preview-manifest.json'))!==sha(manifestRaw)) throw Error('job_changed_during_verification');
  const report={schema:'autospine.animated-workbench-runtime/v1',project_id:project,job_id:job,run_id:receipt.run.run_id,
    job_sha256:sha(jobRaw),bundle_manifest_sha256:sha(manifestRaw),source_addresses:manifest.source_addresses,
    runtime_package:runtimePackage.name,runtime_version:runtimePackage.version,runtime_sha256:sha(runtimeRaw),runtime_package_json_sha256:sha(packageRaw),
    harness_sha256:sha(harnessRaw),tool_sha256:sha(await fs.readFile(new URL(import.meta.url))),browser:await browser.version(),
    files:images,page_errors:errors,result,authority:'none',production_authorized:false};
  await fs.writeFile(path.join(output,'official-runtime-report.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({project,job,passed:result.passed,frames:result.frames.length,max_motion_error_px:result.max_motion_error_px}));
  if (!result.passed) process.exitCode=1;
} finally {if(browser) await browser.close(); await new Promise(resolve=>server.close(resolve));}
