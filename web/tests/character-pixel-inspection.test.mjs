import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

const source=readFileSync(new URL('../character-player-inspection.js',import.meta.url),'utf8');
function load(spine={}){const window={};vm.runInNewContext(source,{window,spine,Float32Array});return window;}
const math=load().characterPixelMath;
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-7,`${a} != ${b}`);
const plain=v=>JSON.parse(JSON.stringify(v));

test('screen CSS scale, translated camera, zoom and framebuffer half-pixel centre',()=>{
 const rect={left:100,top:200,width:200,height:300};
 const camera={position:{x:30,y:-20},viewportWidth:400,viewportHeight:600,zoom:2};
 const at=math.pixel([150,275],rect,800,1200,camera);
 assert.deepEqual(plain(at.pixel),[200,300]);close(at.world[0],-169.5);close(at.world[1],279.5);
 assert.equal(math.pixel([300,250],rect,800,1200,camera),null);
 assert.equal(math.pixel([99,250],rect,800,1200,camera),null);
 assert.equal(math.pixel([150,275],rect,800,1200,{...camera,zoom:NaN}),null);
});

test('barycentric position follows translated or deformed vertices, rejects outside and degenerate',()=>{
 assert.deepEqual(plain(math.barycentric([15,25],[10,20,30,20,10,40],[0,1,2])),[.5,.25,.25]);
 assert.deepEqual(plain(math.barycentric([15,25],[10,20,10,40,30,20],[0,1,2])),[.5,.25,.25]);
 assert.equal(math.barycentric([40,40],[10,20,30,20,10,40],[0,1,2]),null);
 assert.equal(math.barycentric([10,20],[10,20,10,20,10,20],[0,1,2]),null);
});

test('bilinear alpha observes half texel and clamp at texture border',()=>{
 const texture={width:2,height:2,data:new Uint8Array([0,0,0,0,0,0,0,64,0,0,0,128,0,0,0,255])};
 close(math.alpha(texture,[.25,.25]),0);close(math.alpha(texture,[.5,.5]),111.75);
 close(math.alpha(texture,[1,1]),255);close(math.alpha(texture,[-.2,1]),128);
});

test('low alpha combines across all layers regardless of order; no per-attachment gap assumption',()=>{
 const hits=[{alpha:5},{alpha:5}];const a=math.classify(hits,10),b=math.classify(hits.reverse(),10);
 assert.equal(a.kind,'covered');assert.equal(a.upper,b.upper);assert.ok(a.upper>8);
 assert.equal(math.classify([{alpha:2}],2).kind,'transparent_texture');
 assert.equal(math.classify([],0).kind,'no_mesh');
 assert.equal(math.classify([],40).kind,'sampling_mismatch');
 assert.equal(math.classify([{alpha:255}],0).kind,'sampling_mismatch');
 assert.equal(math.classify([{alpha:255}],255,['clipping']).kind,'unsupported');
 assert.equal(math.classify([{alpha:NaN}],0).kind,'unsupported');
});

class MeshAttachment{
 constructor(sequence){this.sequence=sequence;this.color={a:1};this.worldVerticesLength=6;
  this.triangles=[0,1,2];this.offset=0;}
 computeWorldVertices(_s,_slot,_start,_count,out){out.set([this.offset,0,this.offset+2,0,this.offset,2]);}
}
class RegionAttachment{
 constructor(sequence){this.sequence=sequence;this.color={a:.5};}
 getOffsets(pose){assert.equal(pose.sequenceIndex,1);return 'current offsets';}
 computeWorldVertices(_slot,offsets,out){assert.equal(offsets,'current offsets');out.set([0,0,2,0,2,2,0,2]);}
}
class ClippingAttachment{}
const runtime={MeshAttachment,RegionAttachment,ClippingAttachment};
function fixture(){
 const tex0={},tex1={};
 const sequence={regions:[{texture:tex0},{texture:tex1}],resolveIndex:pose=>pose.sequenceIndex,
  getUVs:index=>{assert.equal(index,1);return [0,0,1,0,1,1,0,1];}};
 const mesh=new MeshAttachment(sequence),region=new RegionAttachment(sequence);
 const slot=(name,attachment)=>({data:{name,blendMode:0},bone:{active:true},
  appliedPose:{attachment,color:{a:.5},sequenceIndex:1}});
 const slots=[slot('mesh',mesh),slot('region',region)];
 const skeleton={color:{a:.8},drawOrder:{appliedPose:slots}};
 const getTexture=texture=>{assert.equal(texture,tex1);return {name:'current.png',width:1,height:1,
  data:[0,0,0,200],linear:true,clamped:true};};
 return {skeleton,slots,mesh,region,getTexture};
}

test('Runtime applied poses, sequence texture, mesh/region APIs and all opacity multipliers',()=>{
 const w=load(runtime),f=fixture();const first=w.inspectCharacterPixel(f.skeleton,[.25,.5],f.getTexture);
 assert.equal(first.limitations.length,0);assert.deepEqual(plain(first.hits.map(h=>h.slot)),['mesh','region']);
 close(first.hits[0].sourceAlpha,200);close(first.hits[0].alpha,80);close(first.hits[1].alpha,40);
 // A new world pose changes ownership immediately; no cached setup positions.
 f.mesh.offset=20;
 const second=w.inspectCharacterPixel(f.skeleton,[.25,.5],f.getTexture);
 assert.deepEqual(plain(second.hits.map(h=>h.slot)),['region']);
 f.slots[1].bone.active=false;
 assert.equal(w.inspectCharacterPixel(f.skeleton,[.25,.5],f.getTexture).hits.length,0);
});

test('unsupported clipping, blend and filters remain diagnostic, never inferred safe',()=>{
 const w=load(runtime),f=fixture();f.slots[0].data.blendMode=1;
 f.slots.push({bone:{active:true},appliedPose:{attachment:new ClippingAttachment()}});
 const result=w.inspectCharacterPixel(f.skeleton,[.25,.5],texture=>({...f.getTexture(texture),linear:false,clamped:false}));
 assert.equal(result.limitations.length,4);
 assert.equal(w.characterPixelMath.classify(result.hits,120,result.limitations).kind,'unsupported');
});

test('missing textures cannot be mistaken for missing mesh',()=>{
 const w=load(runtime),f=fixture();f.mesh.sequence.regions[1].texture=null;
 const result=w.inspectCharacterPixel(f.skeleton,[.25,.5],()=>assert.fail('must not read absent texture'));
 assert.equal(result.hits.length,0);assert.equal(result.limitations.length,1);
 assert.equal(w.characterPixelMath.classify(result.hits,0,result.limitations).kind,'unsupported');
});
