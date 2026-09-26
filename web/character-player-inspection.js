window.createCharacterInspection=function(context,renderer,redraw){
 let focus=null, triangle=null;
 const defaults=()=>{const i=context.info;renderer.camera.setViewport(i.width,i.height);renderer.camera.position.x=i.left+i.width/2;renderer.camera.position.y=i.bottom+i.height/2;renderer.camera.update();};
 window.addEventListener('message',event=>{
  const m=event.data;
  if(event.source!==parent||event.origin!==location.origin||m?.type!=='audit-focus'||m.artifact!==context.artifact_sha256)return;
  if(!Array.isArray(m.regions)||!m.regions.length||!m.regions.every(id=>context.skeleton.slots.some(s=>s.name===id)))return;
  focus=m;redraw();
 });
 parent.postMessage({type:'audit-player-ready'},location.origin);
 return {
  setTriangle(slot,index){
   if(slot===null){triangle=null;redraw();return true;}
   const mesh=context.skeleton.skins?.[0]?.attachments?.[slot]?.[slot];
   if(!mesh||!Number.isInteger(index)||index<0||index*3+2>=mesh.triangles?.length)return false;
   triangle={slot,index};redraw();return true;
  },
  setRegions(regions,mode){
   if(!['full','isolate','hide'].includes(mode)||!Array.isArray(regions)||
      !regions.every(id=>context.skeleton.slots.some(s=>s.name===id)))return false;
   focus=mode==='full'||!regions.length?null:{regions:[...new Set(regions)],isolated:mode==='isolate',hidden:mode==='hide',keepCamera:true};
   redraw();return true;
  },
  prepare(skeleton){
   defaults();if(!focus){window.characterInspectionState={regions:[],isolated:false,hidden:false};return;}
   if(focus.hidden)for(const slot of skeleton.slots)if(focus.regions.includes(slot.data.name))slot.appliedPose.setAttachment(null);
   if(focus.isolated){
    for(const slot of skeleton.slots)if(!focus.regions.includes(slot.data.name))slot.appliedPose.setAttachment(null);
    const b=focus.keepCamera?null:skeleton.getBoundsRect();
    if(b&&[b.x,b.y,b.width,b.height].every(Number.isFinite)&&b.width>0&&b.height>0){
     const ratio=context.info.width/context.info.height,h=Math.max(b.height*1.4,b.width*1.4/ratio,80);
     renderer.camera.setViewport(h*ratio,h);renderer.camera.position.x=b.x+b.width/2;renderer.camera.position.y=b.y+b.height/2;renderer.camera.update();
    }
   }
   window.characterInspectionState={regions:focus.regions,isolated:focus.isolated,hidden:!!focus.hidden,bone:focus.bone};
  },draw(skeleton){
   window.characterTriangleInspection=null;
   if(triangle){
    const slot=skeleton.findSlot(triangle.slot),attachment=slot?.appliedPose.attachment;
    if(attachment?.computeWorldVertices&&attachment.triangles?.length>triangle.index*3+2){
     const world=new Float32Array(attachment.worldVerticesLength);
     attachment.computeWorldVertices(skeleton,slot,0,world.length,world,0,2);
     const ids=attachment.triangles.slice(triangle.index*3,triangle.index*3+3);
     const points=Array.from(ids,i=>[world[i*2],world[i*2+1]]);
     if(points.flat().every(Number.isFinite)){
      for(let i=0;i<3;i++)renderer.line(...points[i],...points[(i+1)%3],{r:1,g:.8,b:0,a:1});
      window.characterTriangleInspection={...triangle,points};
     }
    }
   }
   if(!focus||!focus.bone)return;
   const debug=renderer.skeletonDebugRenderer;
   for(const k of ['drawRegionAttachments','drawBoundingBoxes','drawMeshHull','drawMeshTriangles','drawPaths','drawSkeletonXY','drawClipping'])debug[k]=false;
   debug.drawBones=true;
   renderer.drawSkeletonDebug(skeleton,skeleton.bones.filter(b=>b.data.name!==focus.bone).map(b=>b.data.name));
  }
 };
};
// Ideal same-pixel alpha provenance. Shared triangle edges may be counted twice,
// so combined alpha is an upper bound, never proof of correct GPU rasterization.
window.characterPixelMath={
 barycentric(point,vertices,ids){
  const [a,b,c]=ids.map(i=>[vertices[i*2],vertices[i*2+1]]);
  const det=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1]);
  if(!Number.isFinite(det)||Math.abs(det)<1e-12)return null;
  const u=((b[1]-c[1])*(point[0]-c[0])+(c[0]-b[0])*(point[1]-c[1]))/det;
  const v=((c[1]-a[1])*(point[0]-c[0])+(a[0]-c[0])*(point[1]-c[1]))/det;
  const weights=[u,v,1-u-v];return weights.every(v=>Number.isFinite(v)&&v>=-1e-8)?weights:null;
 },
 alpha(texture,uv){
  const x=uv[0]*texture.width-.5,y=uv[1]*texture.height-.5;
  const ix=Math.floor(x),iy=Math.floor(y),fx=x-ix,fy=y-iy;let value=0;
  for(const [dx,dy,w] of [[0,0,(1-fx)*(1-fy)],[1,0,fx*(1-fy)],[0,1,(1-fx)*fy],[1,1,fx*fy]]){
   const px=Math.min(texture.width-1,Math.max(0,ix+dx)),py=Math.min(texture.height-1,Math.max(0,iy+dy));
   value+=w*texture.data[(py*texture.width+px)*4+3];
  }
  return Math.min(255,Math.max(0,value));
 },
 pixel(client,rect,width,height,camera){
  if(![...client,rect.left,rect.top,rect.width,rect.height,width,height,camera.position.x,
      camera.position.y,camera.viewportWidth,camera.viewportHeight,camera.zoom].every(Number.isFinite)||
      [rect.width,rect.height,width,height,camera.viewportWidth,camera.viewportHeight,camera.zoom].some(v=>v<=0))return null;
  const x=Math.floor((client[0]-rect.left)/rect.width*width),y=Math.floor((client[1]-rect.top)/rect.height*height);
  if(x<0||y<0||x>=width||y>=height)return null;
  return {pixel:[x,y],world:[camera.position.x+((x+.5)/width-.5)*camera.viewportWidth*camera.zoom,
   camera.position.y+(.5-(y+.5)/height)*camera.viewportHeight*camera.zoom]};
 },
 classify(hits,framebufferAlpha,limitations=[]){
  if(!Number.isFinite(framebufferAlpha)||framebufferAlpha<0||framebufferAlpha>255||
      hits.some(h=>!Number.isFinite(h.alpha)||h.alpha<0||h.alpha>255))return {kind:'unsupported',upper:null};
  const upper=255*(1-hits.reduce((p,h)=>p*(1-Math.min(1,Math.max(0,h.alpha/255))),1));
  if(limitations.length)return {kind:'unsupported',upper};
  if(framebufferAlpha>=8&&upper<8)return {kind:'sampling_mismatch',upper};
  if(upper<8)return {kind:hits.length?'transparent_texture':'no_mesh',upper};
  return {kind:framebufferAlpha<8?'sampling_mismatch':'covered',upper};
 }
};

window.inspectCharacterPixel=function(skeleton,point,getTexture){
 const hits=[],limitations=new Set();let triangles=0;
 const math=window.characterPixelMath;
 for(const slot of skeleton.drawOrder.appliedPose){
  if(!slot.bone.active)continue;
  const pose=slot.appliedPose,attachment=pose.attachment;
  if(attachment instanceof spine.ClippingAttachment){limitations.add('包含裁剪附件');continue;}
  if(!(attachment instanceof spine.MeshAttachment)&&!(attachment instanceof spine.RegionAttachment))continue;
  if(slot.data.blendMode!==0)limitations.add('包含非普通混合');
  let vertices,indices;
  if(attachment instanceof spine.MeshAttachment){
   vertices=new Float32Array(attachment.worldVerticesLength);
   attachment.computeWorldVertices(skeleton,slot,0,vertices.length,vertices,0,2);indices=attachment.triangles;
  }else{
   vertices=new Float32Array(8);attachment.computeWorldVertices(slot,attachment.getOffsets(pose),vertices,0,2);
   indices=[0,1,2,2,3,0];
  }
  if(!Array.from(vertices).every(Number.isFinite)){limitations.add('网格位置无效');continue;}
  triangles+=indices.length/3;if(triangles>100000)throw Error('本次检查超过三角形数量上限');
  const sequence=attachment.sequence,index=sequence.resolveIndex(pose),region=sequence.regions[index];
  if(!region?.texture){limitations.add('纹理未加载');continue;}
  const uvs=sequence.getUVs(index);let texture=null;
  for(let i=0;i<indices.length;i+=3){
   const ids=Array.from(indices.slice(i,i+3)),w=math.barycentric(point,vertices,ids);if(!w)continue;
   if(!texture)texture=getTexture(region.texture);
   if(!texture.linear)limitations.add('非双线性纹理过滤');
   if(!texture.clamped)limitations.add('非边缘截取纹理');
   const uv=[0,1].map(axis=>ids.reduce((v,id,j)=>v+w[j]*uvs[id*2+axis],0));
   if(!uv.every(Number.isFinite)){limitations.add('无法计算纹理位置');continue;}
   const sourceAlpha=math.alpha(texture,uv);
   if(!Number.isFinite(sourceAlpha)){limitations.add('无法读取纹理透明度');continue;}
   const opacity=skeleton.color.a*pose.color.a*attachment.color.a;
   if(!Number.isFinite(opacity)||opacity<0||opacity>1){limitations.add('不支持的透明度');continue;}
   hits.push({slot:slot.data.name,triangle:i/3,texture:texture.name,uv,sourceAlpha,alpha:sourceAlpha*opacity});
  }
 }
 return {hits,limitations:[...limitations]};
};
