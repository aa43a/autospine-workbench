import test from 'node:test';
import assert from 'node:assert/strict';
import {createEditorRenderer} from '../modules/motion-editor-renderer.js';

test('layer edits affect skinned geometry/order, hit-testing, and restore Runtime attachments',async()=>{
  const old={document:globalThis.document,fetch:globalThis.fetch,spine:globalThis.spine,getComputedStyle:globalThis.getComputedStyle};
  const draw=[];
  class MeshAttachment{
    constructor(){this.worldVerticesLength=6;this.triangles=[0,1,2];}
    computeWorldVertices(_sk,slot,start,count,out,offset,stride){
      // Stand in for Runtime skinning with world translation already applied.
      const values=[10,20,14,20,10,24];
      for(let i=0;i<count/2;i++){out[offset+i*stride]=values[start+i*2]+slot.shift;out[offset+i*stride+1]=values[start+i*2+1];}
    }
  }
  const mesh=new MeshAttachment(),original=mesh.computeWorldVertices;
  class Skeleton{
    constructor(){this.slots=['back','front'].map(name=>({data:{name},bone:{active:true},appliedPose:{attachment:mesh},shift:0}));this.drawOrder={appliedPose:[...this.slots]};this.bones=[];}
    setupPose(){} updateWorldTransform(){}
  }
  class SceneRenderer{
    constructor(){this.camera={setViewport(){},position:{},update(){}};}
    begin(){}end(){}dispose(){}
    drawSkeleton(sk){draw.push(sk.drawOrder.appliedPose.map(slot=>{const values=new Float32Array(6);slot.appliedPose.attachment.computeWorldVertices(sk,slot,0,6,values,0,2);return {slot:slot.data.name,values:Array.from(values)};}));}
  }
  let overlay,clears=0;
  const ctx={clearRect(){clears++;},beginPath(){},moveTo(){},lineTo(){},closePath(){},stroke(){},strokeRect(){}};
  const parent={style:{},scrollLeft:0,scrollTop:0,append(value){overlay=value;},getBoundingClientRect:()=>({left:0,top:0})};
  const gl={viewport(){},clearColor(){},clear(){},isContextLost:()=>false,COLOR_BUFFER_BIT:1};
  const canvas={parentElement:parent,getContext:()=>gl,getBoundingClientRect:()=>({left:100,top:50,width:200,height:300})};
  globalThis.document={head:{append:script=>queueMicrotask(()=>script.onload())},createElement:()=>({style:{},setAttribute(){},remove(){},getContext:()=>ctx})};
  globalThis.getComputedStyle=()=>({position:'relative'});
  globalThis.spine={MeshAttachment,RegionAttachment:class{},Skeleton,SceneRenderer,Physics:{update:0},TextureAtlas:class{pages=[];dispose(){}},SkeletonJson:class{readSkeletonData(){return {}; }},AtlasAttachmentLoader:class{}};
  const scene={artifact_sha256:'a',atlas:'',info:{width:100,height:100,left:0,bottom:0},skeleton:{slots:[{name:'back'},{name:'front'}],skins:[{attachments:Object.fromEntries(['back','front'].map(slot=>[slot,{[slot]:{type:'mesh',vertices:[1,0,0,0,1],uvs:[0,0]}}]))}]}};
  const originalDocument=structuredClone(scene.skeleton);
  globalThis.fetch=async url=>({ok:true,json:async()=>url.endsWith('scene.json')?scene:{artifact_sha256:'a',runtime_sha256:'r'}});
  try{
    const renderer=await createEditorRenderer(canvas,'/');
    assert.equal(overlay.style.background,'transparent');assert.equal(overlay.style.minHeight,'0');assert.equal(overlay.style.outline,'none');
    renderer.draw();assert.deepEqual(renderer.layers().map(row=>row.slot),['back','front']);
    const edits={profile:'slot-world-affine-v1',draw_order:['front','back'],transforms:[{slot:'back',dx:10,dy:0,rotation:0,scaleX:1,scaleY:1}]};
    renderer.layerEdits(edits);renderer.draw();
    assert.deepEqual(draw.at(-1),[{slot:'front',values:[10,20,14,20,10,24]},{slot:'back',values:[20,20,24,20,20,24]}]);
    assert.equal(mesh.computeWorldVertices,original,'temporary wrapper must be restored even for shared attachments');
    assert.deepEqual(renderer.layers().map(row=>row.slot),['front','back']);
    assert.equal(renderer.pickLayer(142,258),'back'); // world (21,21), letterboxed canvas.
    assert.equal(renderer.pickLayer(142,60),null);
    assert.deepEqual(renderer.canvasDelta(10,10),{x:5,y:-5});
    const copy=renderer.layerEdits();copy.transforms[0].dx=400;assert.equal(renderer.layerEdits().transforms[0].dx,10);
    renderer.layerEdits(null);renderer.draw();assert.deepEqual(draw.at(-1)[0].values,[10,20,14,20,10,24]);
    assert.deepEqual(scene.skeleton,originalDocument);const previous=clears;renderer.clear();assert.equal(clears,previous+1);renderer.dispose();
  }finally{for(const [key,value] of Object.entries(old)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}}
});
