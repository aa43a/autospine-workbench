// Numeric official Runtime in Node. Does not launch, control or capture a browser.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import vm from 'node:vm';

const [fixturePath,runtimePath]=process.argv.slice(2);
const fixture=JSON.parse(readFileSync(fixturePath,'utf8'));
const runtime=readFileSync(runtimePath);
assert.equal(createHash('sha256').update(runtime).digest('hex'),fixture.runtime_sha256);
const sandbox={window:{},Float32Array,Uint8Array,console};vm.createContext(sandbox);
vm.runInContext(runtime.toString(),sandbox);
vm.runInContext(readFileSync(new URL('../web/character-player-inspection.js',import.meta.url),'utf8'),sandbox);
const {spine,window}=sandbox,atlas=new spine.TextureAtlas(fixture.atlas),textures=new Map();
for(const page of atlas.pages){
 const bytes=fixture.textures[page.name];assert.ok(bytes,`missing page ${page.name}`);
 const texture={getImage:()=>({width:bytes.width,height:bytes.height}),setFilters(){},setWraps(){}};
 page.setTexture(texture);
 textures.set(texture,{name:page.name,width:bytes.width,height:bytes.height,data:Buffer.from(bytes.rgba,'base64'),
  linear:page.minFilter===spine.TextureFilter.Linear&&page.magFilter===spine.TextureFilter.Linear,
  clamped:page.uWrap===spine.TextureWrap.ClampToEdge&&page.vWrap===spine.TextureWrap.ClampToEdge});
}
const data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(fixture.skeleton);
const skeleton=new spine.Skeleton(data),state=new spine.AnimationState(new spine.AnimationStateData(data));
skeleton.setupPose();state.setAnimation(0,fixture.animation,false);state.update(fixture.time);state.apply(skeleton);
skeleton.updateWorldTransform(spine.Physics.update);
const {width,height,left,bottom}=fixture.info,[imageWidth,imageHeight]=fixture.image_size;
const camera={position:{x:left+width/2,y:bottom+height/2},viewportWidth:width,viewportHeight:height,zoom:1};
const math=window.characterPixelMath,results=[];
for(const row of fixture.rows){
 const at=math.pixel(row.pixel.map(v=>v+.5),{left:0,top:0,width:imageWidth,height:imageHeight},imageWidth,imageHeight,camera);
 for(let i=0;i<2;i++)assert.ok(Math.abs(at.world[i]-row.world[i])<1e-8);
 const observed=window.inspectCharacterPixel(skeleton,at.world,texture=>textures.get(texture));
 assert.equal(observed.limitations.length,0,observed.limitations.join(';'));
 assert.equal(observed.hits.length,row.hits.length);
 for(let i=0;i<row.hits.length;i++){
  const actual=observed.hits[i],expected=row.hits[i];assert.equal(actual.slot,expected.slot);
  assert.equal(actual.triangle,expected.triangle);
  assert.ok(Math.abs(actual.alpha-expected.bilinear_source_rgba[3])<.002,`alpha ${actual.alpha}`);
 }
 const classification=math.classify(observed.hits,row.framebuffer_rgba[3],observed.limitations);
 assert.equal(classification.kind,row.framebuffer_rgba[3]<8?'transparent_texture':'covered');
 results.push({pixel:row.pixel,framebuffer_alpha:row.framebuffer_rgba[3],...classification,
  hits:observed.hits.map(h=>({slot:h.slot,triangle:h.triangle,alpha:h.alpha}))});
}
console.log(JSON.stringify({candidate:fixture.candidate,time:fixture.time,screenshot_sha256:fixture.screenshot_sha256,
 runtime_sha256:fixture.runtime_sha256,scope:'node_official_runtime_cpu_vs_existing_capture_no_new_gpu_capture',
 authority:'none',selected:false,results},null,2));
