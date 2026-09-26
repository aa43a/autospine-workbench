// Component logic with an in-memory DOM/GL double, not a browser test.
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

async function player(){
 class Element{
  constructor(){this.value='';this.checked=false;this.style={};this.children=[];this.events={};}
  append(...children){this.children.push(...children);if(!this.value&&children[0]?.value)this.value=children[0].value;}
  replaceChildren(){this.children=[];}
  addEventListener(name,fn){this.events[name]=fn;}
  closest(){return this;}
  getBoundingClientRect(){return {left:0,top:0,width:200,height:200};}
 }
 const elements=new Map(),el=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
 let lost=false,reads=0;
 const gl={RGBA:1,UNSIGNED_BYTE:2,NO_ERROR:0,COLOR_BUFFER_BIT:4,
  viewport(){},clearColor(){},clear(){},isContextLost:()=>lost,getError:()=>0,
  readPixels(_x,_y,_w,_h,_format,_type,out){reads++;out.set([1,2,3,128]);}};
 const canvas=new Element();canvas.getContext=()=>gl;
 const document={getElementById:el,querySelector:()=>canvas,addEventListener(){},createElement:kind=>{
  const node=new Element();if(kind==='canvas')node.getContext=()=>({drawImage(){},
   getImageData:()=>({data:new Uint8Array([0,0,0,128,0,0,0,128,0,0,0,128,0,0,0,128])})});return node;
 }};
 const context={artifact_sha256:'candidate-A',info:{left:0,bottom:0,width:2,height:2},
  textures:{'page.png':'data:image/png;stub'},atlas:'stub',skeleton:{slots:[{name:'body'}]}};
 let texture;
 class TextureAtlas{constructor(){this.pages=[{name:'page.png',minFilter:1,magFilter:1,uWrap:2,vWrap:2,
  setTexture(value){texture=value;}}];}}
 class MeshAttachment{
  constructor(){this.triangles=[0,1,2];this.color={a:1};this.worldVerticesLength=6;
   this.sequence={resolveIndex:()=>0,getUVs:()=>[0,0,1,0,0,1],regions:[{texture}]};}
  computeWorldVertices(_s,_slot,_start,_count,out){out.set([0,0,2,0,0,2]);}
 }
 class Skeleton{constructor(){this.color={a:1};this.slots=[{bone:{active:true},data:{name:'body',blendMode:0},
  appliedPose:{attachment:new MeshAttachment(),color:{a:1},setAttachment(value){this.attachment=value;}}}];
  this.drawOrder={appliedPose:this.slots};}setupPose(){}updateWorldTransform(){} }
 const data={animations:[{name:'motion'}],findAnimation:()=>({duration:1})};
 const spine={TextureAtlas,GLTexture:class{},TextureFilter:{Linear:1},TextureWrap:{ClampToEdge:2},
  AtlasAttachmentLoader:class{},SkeletonJson:class{readSkeletonData(){return data;}},Skeleton,
  AnimationState:class{setAnimation(){}update(){}apply(){}},AnimationStateData:class{},Physics:{update:0},
  MeshAttachment,RegionAttachment:class{},ClippingAttachment:class{},
  SceneRenderer:class{constructor(){this.camera={zoom:1,position:{},setViewport(w,h){this.viewportWidth=w;this.viewportHeight=h;},update(){}};}
   begin(){}drawSkeleton(){}end(){}}};
 const window={spine,addEventListener(){}};let fetches=0;
 const sandbox={window,spine,document,Float32Array,Uint8Array,URL,console,
  parent:{postMessage(){}},location:{href:'http://fixture.invalid/player.html',origin:'http://fixture.invalid'},
  Image:class{constructor(){this.width=2;this.height=2;}async decode(){}},
  fetch:async()=>{fetches++;return {ok:true,json:async()=>context};},
  requestAnimationFrame(){},performance:{now:()=>0},setTimeout,clearTimeout};
 vm.createContext(sandbox);
 for(const filename of ['character-player-inspection.js','character-player.js'])
  vm.runInContext(readFileSync(new URL('../'+filename,import.meta.url),'utf8'),sandbox);
 for(let i=0;i<50&&!window.characterPlayerReady&&!window.characterPlayerError;i++)await new Promise(setImmediate);
 assert.equal(window.characterPlayerError,undefined);assert.equal(window.characterPlayerReady,true);
 return {window,el,canvas,reads:()=>reads,fetches:()=>fetches,lose:()=>{lost=true;}};
}

test('click pauses and binds evidence to exact candidate/time; seek and disabling clear old results',async()=>{
 const p=await player();p.el('pixel-check').checked=true;p.el('pixel-check').onchange();
 p.el('play').onclick();assert.equal(p.window.characterPlayerState.playing,true);
 p.canvas.events.click({clientX:50,clientY:150});
 assert.equal(p.window.characterPlayerState.playing,false);
 const hit=p.window.characterPixelInspection;
 assert.equal(hit.artifact,'candidate-A');assert.equal(hit.animation,'motion');assert.equal(hit.time,0);
 assert.equal(hit.kind,'covered');assert.equal(hit.hits[0].slot,'body');assert.equal(hit.selected,false);
 assert.equal(hit.authority,'none');assert.equal(p.reads(),1);
 p.window.characterPlayerControl.seek(.4);assert.equal(p.window.characterPixelInspection,null);
 p.canvas.events.click({clientX:50,clientY:150});assert.equal(p.window.characterPixelInspection.time,.4);
 p.el('pixel-check').checked=false;p.el('pixel-check').onchange();assert.equal(p.window.characterPixelInspection,null);
 assert.equal(p.fetches(),1,'inspection must not write or fetch any verdict');
});

test('partial view and lost framebuffer never produce a complete-character conclusion',async()=>{
 const p=await player();p.el('pixel-check').checked=true;p.el('pixel-check').onchange();
 p.window.characterPlayerControl.inspectRegions(['body'],'hide');
 p.canvas.events.click({clientX:50,clientY:150});
 assert.equal(p.reads(),0);assert.equal(p.window.characterPixelInspection,null);
 assert.match(p.el('pixel-result').textContent,/恢复完整角色/);
 p.window.characterPlayerControl.inspectRegions([],'full');p.lose();
 p.canvas.events.click({clientX:50,clientY:150});
 assert.equal(p.reads(),0);assert.equal(p.window.characterPixelInspection,null);
 assert.match(p.el('pixel-result').textContent,/上下文已丢失/);
});
