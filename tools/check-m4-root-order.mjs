// Isolated draw-order counterfactual. Does not publish an artifact or record acceptance.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE);
const [input,output]=process.argv.slice(2),root=path.resolve(input);
const hash=b=>createHash('sha256').update(b).digest('hex');
const original=await fs.readFile(path.join(root,'player-assets/scene.json'));
const before=JSON.parse(original),after=structuredClone(before);
const doc=after.skeleton,material='m4-root-material',body='layer-006';
assert.ok(Object.values(doc.animations).every(a=>!a.drawOrder),'animated order needs separate remapping');
const index=doc.slots.findIndex(s=>s.name===material),bodyIndex=doc.slots.findIndex(s=>s.name===body);
assert.ok(index>=0&&bodyIndex>index);
const [slot]=doc.slots.splice(index,1);
doc.slots.splice(doc.slots.findIndex(s=>s.name===body)+1,0,slot);
// Slot names keep attachment/deform identities; weights refer to bones, not slot indices.
const restored=structuredClone(doc);restored.slots=before.skeleton.slots;
assert.deepEqual(restored,before.skeleton);
const experiment=hash(JSON.stringify({parent:before.artifact_sha256,skeleton:doc,profile:'root-order-counterfactual-v1'}));
after.artifact_sha256=experiment;
const changed=Buffer.from(JSON.stringify(after));
await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true,
 args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const errors=[],pages=[],times=[0,.7,1.05,1.725,2.4,4];
try{
 for(const [label,scene] of [['behind',original],['front',changed]]){
  const page=await browser.newPage({viewport:{width:1280,height:1100}});
  page.on('pageerror',e=>errors.push(String(e)));
  await page.route('http://m4-order.test/**',async route=>{
   const name=path.resolve(root,'.'+decodeURIComponent(new URL(route.request().url()).pathname));
   assert.ok(name.startsWith(root+path.sep));
   const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json'};
   await route.fulfill({body:name===path.join(root,'player-assets/scene.json')?scene:await fs.readFile(name),
    contentType:types[path.extname(name)]||'application/octet-stream'});
  });
  await page.goto('http://m4-order.test/player.html');
  await page.waitForFunction(()=>window.characterPlayerReady||window.characterPlayerError,null,{timeout:120000});
  assert.equal(await page.evaluate(()=>window.characterPlayerError),undefined);
  assert.equal(await page.evaluate(()=>window.characterPlayerControl.artifact),label==='behind'?before.artifact_sha256:experiment);
  for(const time of times){
   assert.equal(await page.evaluate(t=>window.characterPlayerControl.seek(t),time),true);
   await page.locator('canvas').screenshot({path:path.join(output,`${label}-${time}.png`)});
  }
  await page.evaluate(()=>window.characterPlayerControl.seek(0));
  assert.deepEqual(await page.locator('canvas').screenshot(),await fs.readFile(path.join(output,`${label}-0.png`)));
  pages.push(page);
 }
 assert.deepEqual(errors,[]);
 assert.equal(hash(await fs.readFile(path.join(root,'player-assets/scene.json'))),hash(original));
 const rows=times.map(time=>`<section><h2>${time} 秒</h2><div><figure><img src="behind-${time}.png"><figcaption>连接片后置（原实验）</figcaption></figure><figure><img src="front-${time}.png"><figcaption>连接片前置（对照，未采用）</figcaption></figure></div></section>`).join('');
 await fs.writeFile(path.join(output,'index.html'),`<!doctype html><meta charset="utf-8"><title>肩部连接片前后对照</title><style>body{background:#17232e;color:white;font:16px sans-serif}section div{display:flex}figure{margin:8px}img{max-width:45vw}p{max-width:1000px}</style><h1>肩部连接片前后对照</h1><p>只改变连接片绘制顺序；原动作、纹理、权重保持一致。前置不代表源深度正确，也不代表视觉接受。未修改工作台候选。</p>${rows}`);
 const report={parent:before.artifact_sha256,experiment,source_scene_sha256:hash(original),
  counterfactual_scene_sha256:hash(changed),times,browser:browser.version(),errors,reverse_seek:true,
  original_unchanged:true,authority:'none',selected:false,scope:'six_pose_GPU_counterfactual_not_full_animation_acceptance'};
 await fs.writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2));
 console.log(JSON.stringify(report));
}finally{await browser.close();}
