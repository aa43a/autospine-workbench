// Isolated official Runtime viewport. Never edits the saved character document.
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
  const {width,height,left,bottom}=scene.info;
  if(![width,height,left,bottom].every(Number.isFinite)||width<1||height<1||width>4096||height>4096){atlas.dispose();throw Error('角色画布范围无效');}
  canvas.width=width;canvas.height=height;
  const renderer=new spine.SceneRenderer(canvas,gl);
  renderer.camera.setViewport(width,height);renderer.camera.position.x=left+width/2;renderer.camera.position.y=bottom+height/2;renderer.camera.update();
  const parser=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas));
  let data=parser.readSkeletonData({...scene.skeleton,animations:{}}),hasAnimation=false;
  const clear=()=>{gl.viewport(0,0,width,height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);};
  return {document:scene.skeleton,artifact:scene.artifact_sha256,
    animation(value){data=parser.readSkeletonData({...scene.skeleton,animations:{'camera-preview':value}});hasAnimation=true;},
    draw(time=0){
      if(gl.isContextLost())throw Error('角色画布已失效，请刷新');
      const skeleton=new spine.Skeleton(data);skeleton.setupPose();
      if(hasAnimation){const state=new spine.AnimationState(new spine.AnimationStateData(data));state.setAnimation(0,'camera-preview',false);state.update(time);state.apply(skeleton);}
      skeleton.updateWorldTransform(spine.Physics.update);clear();renderer.begin();renderer.drawSkeleton(skeleton);renderer.end();
      return skeleton.bones.filter(b=>['root','upperarm_l','forearm_l','thigh_l','calf_l'].includes(b.data.name))
        .map(b=>{const p=b.appliedPose;return {name:b.data.name,rotation:p.rotation,scaleX:p.scaleX,scaleY:p.scaleY,
          matrix:[p.a,p.b,p.c,p.d,p.worldX,p.worldY]};});
    },clear,
    dispose(){atlas.dispose();renderer.dispose();clear();},
  };
}
