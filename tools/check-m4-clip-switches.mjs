// Real framebuffer captures at topology boundaries and interval interiors.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [url,deps,chrome,segmentsPath,output]=process.argv.slice(2);
const raw=await fs.readFile(segmentsPath),report=JSON.parse(raw);
const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
const {chromium}=await import(pathToFileURL(path.resolve(deps,'node_modules/playwright-core/index.mjs')));
const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
  const page=await browser.newPage({viewport:{width:1600,height:1200}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(url);
  await page.waitForFunction(()=>window.reachComparisonState?.ready||window.reachComparisonError,null,{timeout:120000});
  assert.equal(await page.evaluate(()=>window.reachComparisonError),undefined);
  const state=await page.evaluate(()=>window.reachComparisonState);
  assert.equal(state.artifacts[0],report.parent);
  await fs.mkdir(output,{recursive:false});
  const samples=[];
  for(const [i,segment] of report.segments.entries()) {
    const times=[['interior',(segment.start+segment.end)/2]];
    if(i)times.push(['prior',segment.start-1e-6],['switch',segment.start],['following',segment.start+1e-6]);
    for(const [label,time] of times) {
      assert.ok(time>=0&&time<=state.duration+1e-6);
      const captures=await page.evaluate(time=>['left','right'].map(id=>{
        const w=document.getElementById(id).contentWindow;
        if(!w.characterPlayerControl.seek(time))throw Error('seek rejected');
        const canvas=w.document.querySelector('canvas');
        return {time:w.characterPlayerState.time,png:canvas.toDataURL('image/png'),width:canvas.width,height:canvas.height};
      }),time);
      const files=[];
      for(const [side,capture] of captures.entries()) {
        assert.ok(Math.abs(capture.time-time)<1e-8);
        const name=`${i}-${label}-${side}.png`,bytes=Buffer.from(capture.png.split(',')[1],'base64');
        await fs.writeFile(path.join(output,name),bytes);
        files.push({name,sha256:digest(bytes),width:capture.width,height:capture.height});
      }
      samples.push({segment:i,label,time,files});
    }
  }
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'capture.json'),JSON.stringify({authority:'none',artifacts:state.artifacts,segments_sha256:digest(raw),samples,errors},null,2));
  console.log(JSON.stringify({samples:samples.length,errors}));
} finally {await browser.close();}
