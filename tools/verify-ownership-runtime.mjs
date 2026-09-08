// Local opt-in harness. Official packages are external and never bundled in output.
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [root,dependencies,chrome]=process.argv.slice(2);
if(!root||!dependencies||!chrome)throw new Error('usage: root dependencies chrome');
const {chromium}=await import(pathToFileURL(path.join(dependencies,'node_modules/playwright-core/index.mjs')));
const runtime=path.join(dependencies,'node_modules/@esotericsoftware/spine-webgl/dist/iife/spine-webgl.js');
const runtimePackage=JSON.parse(await fs.readFile(path.join(dependencies,'node_modules/@esotericsoftware/spine-webgl/package.json')));
if(runtimePackage.name!=='@esotericsoftware/spine-webgl'||runtimePackage.version!=='4.3.13')throw new Error('runtime_version_mismatch');
const files=new Map([['/runtime.js',runtime],['/ownership-runtime.js',new URL('./ownership-runtime.js',import.meta.url)],['/',new URL('./ownership-runtime.html',import.meta.url)]]);
for(const name of ['alice','lingxian','crino']){
  const folder=path.resolve(root,name),manifest=JSON.parse(await fs.readFile(path.join(folder,'preview-manifest.json')));
  for(const [file,digest] of Object.entries(manifest.files)){
    const resolved=path.resolve(folder,file);if(!resolved.startsWith(folder+path.sep))throw new Error('file_escape');
    const raw=await fs.readFile(resolved);if(crypto.createHash('sha256').update(raw).digest('hex')!==digest)throw new Error('file_changed');
    files.set('/'+name+'/'+file,resolved);
  }
  files.set('/'+name+'/preview-manifest.json',path.join(folder,'preview-manifest.json'));
}
const server=http.createServer(async(req,res)=>{
  try{const file=files.get(new URL(req.url,'http://localhost').pathname);if(!file){res.writeHead(404);res.end();return;}
    const raw=await fs.readFile(file),ext=path.extname(String(file));res.setHeader('Content-Type',({'.js':'text/javascript','.png':'image/png','.json':'application/json','.html':'text/html'})[ext]||'text/plain');res.end(raw);
  }catch{res.writeHead(500);res.end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const url='http://127.0.0.1:'+server.address().port;
console.log('Preview URL: '+url+'/?character=alice');
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const results=[];
try{
  for(const name of ['alice','lingxian','crino']){
    const page=await browser.newPage({viewport:{width:1100,height:1100}});const errors=[];page.on('pageerror',e=>errors.push(String(e)));
    await page.goto(url+'/?character='+name);await page.waitForFunction(()=>window.ready||window.failure,{},{timeout:60000});
    const failure=await page.evaluate(()=>window.failure);if(failure)throw new Error(failure);
    const result=await page.evaluate(()=>window.verifyFrames());
    result.character=name;result.page_errors=errors;
    result.bundle_manifest_sha256=crypto.createHash('sha256').update(await fs.readFile(path.join(root,name,'preview-manifest.json'))).digest('hex');
    result.passed=!errors.length&&result.max_page_uv_error<=1e-6&&result.max_setup_error_px<=.001&&result.max_motion_error_px<=.001&&result.outside_viewport_coordinates===0&&result.animation_changed&&result.frames.every(f=>f.channels_over_one===0&&f.visible_pixels>0);
    await page.screenshot({path:path.join(root,name+'-runtime-setup.png')});
    await page.evaluate(()=>window.renderAt(.5));await page.screenshot({path:path.join(root,name+'-runtime-bend.png')});
    results.push(result);console.log(name+': '+JSON.stringify({passed:result.passed,uv:result.max_page_uv_error,setup:result.max_setup_error_px,maxPixel:Math.max(...result.frames.map(f=>f.max_channel_error))}));
    await page.close();
  }
  const report={runtime_package:'@esotericsoftware/spine-webgl',runtime_version:'4.3.13',runtime_sha256:crypto.createHash('sha256').update(await fs.readFile(runtime)).digest('hex'),browser:await browser.version(),authority:'none',production_authorized:false,results};
  await fs.writeFile(path.join(root,'official-runtime-report.json'),JSON.stringify(report,null,2));
  if(results.some(r=>!r.passed))process.exitCode=1;
}finally{await browser.close();if(process.env.KEEP_PREVIEW!=='1'||results.length!==3||results.some(r=>!r.passed))server.close();}
