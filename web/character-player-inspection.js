window.createCharacterInspection=function(context,renderer,redraw){
 let focus=null;
 const defaults=()=>{const i=context.info;renderer.camera.setViewport(i.width,i.height);renderer.camera.position.x=i.left+i.width/2;renderer.camera.position.y=i.bottom+i.height/2;renderer.camera.update();};
 window.addEventListener('message',event=>{
  const m=event.data;
  if(event.source!==parent||event.origin!==location.origin||m?.type!=='audit-focus'||m.artifact!==context.artifact_sha256)return;
  if(!Array.isArray(m.regions)||!m.regions.length||!m.regions.every(id=>context.skeleton.slots.some(s=>s.name===id)))return;
  focus=m;redraw();
 });
 parent.postMessage({type:'audit-player-ready'},location.origin);
 return {
  prepare(skeleton){
   defaults();if(!focus)return;
   if(focus.isolated){
    for(const slot of skeleton.slots)if(!focus.regions.includes(slot.data.name))slot.appliedPose.setAttachment(null);
    const b=skeleton.getBoundsRect();
    if([b.x,b.y,b.width,b.height].every(Number.isFinite)&&b.width>0&&b.height>0){
     const ratio=context.info.width/context.info.height,h=Math.max(b.height*1.4,b.width*1.4/ratio,80);
     renderer.camera.setViewport(h*ratio,h);renderer.camera.position.x=b.x+b.width/2;renderer.camera.position.y=b.y+b.height/2;renderer.camera.update();
    }
   }
   window.characterInspectionState={regions:focus.regions,isolated:focus.isolated,bone:focus.bone};
  },draw(skeleton){
   if(!focus)return;
   const debug=renderer.skeletonDebugRenderer;
   for(const k of ['drawRegionAttachments','drawBoundingBoxes','drawMeshHull','drawMeshTriangles','drawPaths','drawSkeletonXY','drawClipping'])debug[k]=false;
   debug.drawBones=true;
   renderer.drawSkeletonDebug(skeleton,skeleton.bones.filter(b=>b.data.name!==focus.bone).map(b=>b.data.name));
  }
 };
};
