// Isolated official Runtime viewport. Never edits the saved character document.
import {editableLayer,layerBounds,transformLayerVertices,normalizeLayerEdits,pointInLayer,canvasContentRect,canvasWorldPoint} from './motion-layer-transform.js';
let runtimePromise=null,runtimeHash=null;
async function runtime(url,hash){
  if(runtimePromise){if(runtimeHash!==hash)throw Error('Runtime 版本变化，请刷新编辑页');return runtimePromise;}
  runtimeHash=hash;
  runtimePromise=new Promise((resolve,reject)=>{
    const script=document.createElement('script');script.src=url;
    script.onload=()=>resolve();script.onerror=()=>{runtimePromise=null;runtimeHash=null;script.remove();reject(Error('Runtime 加载失败'));};
    document.head.append(script);
  });return runtimePromise;
}
export async function createEditorRenderer(canvas,base,current=()=>true){
  const get=async name=>{const response=await fetch(base+name,{cache:'no-store'});if(!response.ok)throw Error(`角色资源读取失败 (${response.status})`);return response.json();};
  const [scene,context]=await Promise.all([get('scene.json'),get('context.json')]);
  if(scene.artifact_sha256!==context.artifact_sha256)throw Error('角色版本不一致，请重新选择');
  await runtime(base+'runtime.js',context.runtime_sha256);
  if(!current())return null;
  const gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:true,antialias:false});
  if(!gl)throw Error('无法创建角色画布');
  const atlas=new spine.TextureAtlas(scene.atlas);
  try{await Promise.all(atlas.pages.map(async page=>{
    if(!scene.textures[page.name])throw Error('角色纹理缺失');
    const image=new Image();image.src=scene.textures[page.name];await image.decode();
    page.setTexture(new spine.GLTexture(gl,image,false,false));
  }));}catch(e){atlas.dispose();throw e;}
  if(!current()){atlas.dispose();return null;}
  let {width,height,left,bottom}=scene.info;
  if(![width,height,left,bottom].every(Number.isFinite)||width<1||height<1||width>4096||height>4096){atlas.dispose();throw Error('角色画布范围无效');}
  canvas.width=width;canvas.height=height;
  const renderer=new spine.SceneRenderer(canvas,gl);
  renderer.camera.setViewport(width,height);renderer.camera.position.x=left+width/2;renderer.camera.position.y=bottom+height/2;renderer.camera.update();
  const parser=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas));
  let data=parser.readSkeletonData({...scene.skeleton,animations:{}}),hasAnimation=false;
  let edits=normalizeLayerEdits(null,[]),selected=null,lastGeometry=new Map(),lastOrder=[],lastBones=new Map();
  const setup=new spine.Skeleton(data);setup.setupPose();setup.updateWorldTransform(spine.Physics.update);
  const slots=setup.slots.map(slot=>slot.data.name),pivots=new Map(),supported=new Set();
  function geometry(skeleton,slot){
    const pose=slot.appliedPose,attachment=pose.attachment;
    if(!slot.bone.active||!attachment)return null;
    let points,triangles;
    if(attachment instanceof spine.MeshAttachment){points=new Float32Array(attachment.worldVerticesLength);attachment.computeWorldVertices(skeleton,slot,0,points.length,points,0,2);triangles=Array.from(attachment.triangles);}
    else if(attachment instanceof spine.RegionAttachment){points=new Float32Array(8);attachment.computeWorldVertices(slot,attachment.getOffsets(pose),points,0,2);triangles=[0,1,2,2,3,0];}
    else return null;
    return {points:Array.from(points),triangles,bounds:layerBounds(points)};
  }
  for(const slot of setup.slots){const g=geometry(setup,slot);if(!g?.bounds)continue;
    pivots.set(slot.data.name,[(g.bounds.left+g.bounds.right)/2,(g.bounds.bottom+g.bounds.top)/2]);
    if(slot.appliedPose.attachment instanceof spine.MeshAttachment&&editableLayer(scene.skeleton,slot.data.name))supported.add(slot.data.name);
  }
  const overlay=document.createElement('canvas');overlay.setAttribute('aria-hidden','true');
  Object.assign(overlay.style,{position:'absolute',pointerEvents:'none',objectFit:'contain',zIndex:'2',background:'transparent',border:'none',outline:'none',boxShadow:'none',margin:'0',padding:'0',minHeight:'0',minWidth:'0'});
  const parent=canvas.parentElement;if(parent){if(getComputedStyle(parent).position==='static')parent.style.position='relative';parent.append(overlay);}
  const overlayContext=overlay.getContext('2d');
  function highlight(){
    overlay.width=width;overlay.height=height;
    if(parent){const r=canvas.getBoundingClientRect(),p=parent.getBoundingClientRect();
      Object.assign(overlay.style,{left:`${r.left-p.left+parent.scrollLeft}px`,top:`${r.top-p.top+parent.scrollTop}px`,width:`${r.width}px`,height:`${r.height}px`});}
    overlayContext?.clearRect(0,0,width,height);const g=lastGeometry.get(selected);if(!g||!overlayContext)return;
    const ctx=overlayContext;ctx.strokeStyle='rgba(255,209,89,.48)';ctx.lineWidth=1;ctx.beginPath();
    for(let i=0;i<g.triangles.length;i+=3){for(let j=0;j<3;j++){const k=g.triangles[i+j]*2,x=g.points[k]-left,y=height-(g.points[k+1]-bottom);if(j)ctx.lineTo(x,y);else ctx.moveTo(x,y);}ctx.closePath();}ctx.stroke();
    const b=g.bounds;ctx.strokeStyle='#ffd159';ctx.lineWidth=2;ctx.strokeRect(b.left-left,height-(b.top-bottom),b.width,b.height);
  }
  const resizeObserver=typeof ResizeObserver==='function'?new ResizeObserver(()=>highlight()):null;
  resizeObserver?.observe(canvas);
  const clear=()=>{gl.viewport(0,0,width,height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);overlayContext?.clearRect(0,0,width,height);};
  return {document:scene.skeleton,artifact:scene.artifact_sha256,bounds:{width,height,left,bottom},
    layers(){const order=lastOrder.length?lastOrder:slots;return order.map(slot=>({slot,label:slot,supported:supported.has(slot),pivot:pivots.get(slot)?.slice()}));},
    layerEdits(value){if(arguments.length){const next=normalizeLayerEdits(value,slots);if(next.transforms.some(edit=>!supported.has(edit.slot)))throw Error('此附件尚不支持网格校正');edits=next;}return structuredClone(edits);},
    getLayerEdits(){return structuredClone(edits);},
    selectLayer(slot){selected=slots.includes(slot)?slot:null;highlight();},
    layerGeometry(slot){return structuredClone(lastGeometry.get(slot)??null);},
    boneMatrix(name){return lastBones.get(name)?.slice()??null;},
    worldPoint(x,y){return canvasWorldPoint(x,y,canvas.getBoundingClientRect(),{width,height,left,bottom});},
    canvasDelta(dx,dy){const box=canvasContentRect(canvas.getBoundingClientRect(),width,height);return {x:dx/box.scale,y:-dy/box.scale};},
    pickLayer(x,y){const point=canvasWorldPoint(x,y,canvas.getBoundingClientRect(),{width,height,left,bottom});if(!point)return null;
      return [...lastOrder].reverse().find(slot=>{const g=lastGeometry.get(slot);return g&&pointInLayer(point,g.points,g.triangles);})??null;},
    viewport(info){
      if(![info.width,info.height,info.left,info.bottom].every(Number.isFinite)||info.width<1||info.height<1||info.width>4096||info.height>4096)throw Error('对照视口无效');
      ({width,height,left,bottom}=info);canvas.width=width;canvas.height=height;
      renderer.camera.setViewport(width,height);renderer.camera.position.x=left+width/2;renderer.camera.position.y=bottom+height/2;renderer.camera.update();
    },
    animation(value){data=parser.readSkeletonData({...scene.skeleton,animations:{'camera-preview':value}});hasAnimation=true;},
    draw(time=0){
      if(gl.isContextLost())throw Error('角色画布已失效，请刷新');
      const skeleton=new spine.Skeleton(data);skeleton.setupPose();
      if(hasAnimation){const state=new spine.AnimationState(new spine.AnimationStateData(data));state.setAnimation(0,'camera-preview',false);state.update(time);state.apply(skeleton);}
      skeleton.updateWorldTransform(spine.Physics.update);
      lastBones=new Map(skeleton.bones.map(b=>{const p=b.appliedPose;return [b.data.name,[p.a,p.b,p.c,p.d,p.worldX,p.worldY]];}));
      if(edits.draw_order.length){const lookup=new Map(skeleton.slots.map(slot=>[slot.data.name,slot]));skeleton.drawOrder.appliedPose.splice(0,skeleton.slots.length,...edits.draw_order.map(slot=>lookup.get(slot)));}
      const transforms=new Map(edits.transforms.map(edit=>[edit.slot,edit])),restore=[];
      // Runtime invokes this method again when drawing. Wrap per attachment only for
      // this draw, retaining each influence's official skinning before world affine.
      for(const slot of skeleton.slots){const edit=transforms.get(slot.data.name),attachment=slot.appliedPose.attachment;
        if(!edit||!(attachment instanceof spine.MeshAttachment))continue;
        const original=attachment.computeWorldVertices,pivot=pivots.get(slot.data.name);
        attachment.computeWorldVertices=function(sk,sl,start,count,out,offset,stride){
          original.call(this,sk,sl,start,count,out,offset,stride);if(sl.data.name!==slot.data.name)return;
          const points=[];for(let i=0;i<count/2;i++)points.push(out[offset+i*stride],out[offset+i*stride+1]);
          const adjusted=transformLayerVertices(points,edit,pivot);for(let i=0;i<count/2;i++){out[offset+i*stride]=adjusted[i*2];out[offset+i*stride+1]=adjusted[i*2+1];}
        };restore.push(()=>{attachment.computeWorldVertices=original;});
      }
      try{lastGeometry=new Map();lastOrder=skeleton.drawOrder.appliedPose.map(slot=>slot.data.name);
        for(const slot of skeleton.drawOrder.appliedPose){const g=geometry(skeleton,slot);if(g)lastGeometry.set(slot.data.name,g);}
        clear();renderer.begin();renderer.drawSkeleton(skeleton);renderer.end();
      }finally{for(const reset of restore.reverse())reset();}highlight();
      return skeleton.bones.filter(b=>['root','upperarm_l','forearm_l','thigh_l','calf_l'].includes(b.data.name))
        .map(b=>{const p=b.appliedPose;return {name:b.data.name,rotation:p.rotation,scaleX:p.scaleX,scaleY:p.scaleY,
          matrix:[p.a,p.b,p.c,p.d,p.worldX,p.worldY]};});
    },clear(){lastGeometry.clear();lastOrder=[];clear();},
    dispose(){resizeObserver?.disconnect();overlay.remove();atlas.dispose();renderer.dispose();clear();},
  };
}
