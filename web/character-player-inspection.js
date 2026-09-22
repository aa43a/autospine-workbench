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
