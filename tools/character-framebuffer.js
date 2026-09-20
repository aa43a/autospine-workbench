/* All attachments share one actual framebuffer; no synthetic rendering fallback. */
(async()=>{
  const canvas=document.querySelector('canvas');
  const gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:true,preserveDrawingBuffer:true,antialias:false});
  if(!gl)throw Error('webgl_unavailable');
  const get=async name=>{const r=await fetch('/'+name);if(!r.ok)throw Error('asset_missing');return r.json();};
  const doc=await get('skeleton.json'),reference=await get('numeric-reference.json');
  const atlas=new spine.TextureAtlas(await(await fetch('/skeleton.atlas')).text());
  await Promise.all(atlas.pages.map(async page=>{
    const img=new Image();img.src='/'+page.name;await img.decode();
    page.setTexture(new spine.GLTexture(gl,img,false,false));
  }));
  const data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(doc);
  if(JSON.stringify(data.animations.map(a=>a.name).sort())!==JSON.stringify(Object.keys(reference.animations).sort()))throw Error('animation_inventory');
  let left=Infinity,bottom=Infinity,right=-Infinity,top=-Infinity;
  const envelopes=[...Object.values(reference.animations),...Object.values(reference.idealAnimations??{}),...(reference.setup?[[reference.setup]]:[])];
  for(const frames of envelopes)for(const frame of frames)for(const points of Object.values(frame.vertices))for(const [x,y]of points){
    if(!Number.isFinite(x)||!Number.isFinite(y))throw Error('nonfinite_reference');
    left=Math.min(left,x);bottom=Math.min(bottom,y);right=Math.max(right,x);top=Math.max(top,y);
  }
  left=Math.floor(left)-8;bottom=Math.floor(bottom)-8;right=Math.ceil(right)+8;top=Math.ceil(top)+8;
  canvas.width=right-left;canvas.height=top-bottom;
  if(canvas.width<1||canvas.height<1||canvas.width>4096||canvas.height>4096)throw Error('framebuffer_size_limit');
  const renderer=new spine.SceneRenderer(canvas,gl),pixels=new Uint8Array(canvas.width*canvas.height*4);
  renderer.camera.setViewport(canvas.width,canvas.height);
  renderer.camera.position.x=(left+right)/2;renderer.camera.position.y=(bottom+top)/2;renderer.camera.update();
  const debug=gl.getExtension('WEBGL_debug_renderer_info');
  window.captureInfo={width:canvas.width,height:canvas.height,left,bottom,context:gl.getContextAttributes(),
    renderer:gl.getParameter(debug?debug.UNMASKED_RENDERER_WEBGL:gl.RENDERER),
    vendor:gl.getParameter(debug?debug.UNMASKED_VENDOR_WEBGL:gl.VENDOR),atlas_pages:atlas.pages.length,slots:data.slots.length};
  window.captureFrame=(animation,index)=>{
    const frame=animation===null?reference.setup:reference.animations[animation]?.[index];if(!frame)throw Error('frame_missing');
    const skeleton=new spine.Skeleton(data),state=new spine.AnimationState(new spine.AnimationStateData(data));
    skeleton.setupPose();
    if(animation!==null){state.setAnimation(0,animation,false);state.update(frame.time);state.apply(skeleton);}
    skeleton.updateWorldTransform(spine.Physics.update);
    const expectedOrder=autospineExpectedDrawOrder(doc,animation,frame.time);
    const actualOrder=skeleton.drawOrder.appliedPose.map(slot=>slot.data.name);
    if(JSON.stringify(expectedOrder)!==JSON.stringify(actualOrder)){
      window.captureFailure={reason_code:'official_draw_order_mismatch',animation,index,time:frame.time,
        expected:expectedOrder,actual:actualOrder};
      throw Error('official_draw_order_mismatch');
    }
    if(JSON.stringify(skeleton.slots.map(s=>s.data.name).sort())!==JSON.stringify(Object.keys(frame.vertices).sort()))throw Error('slot_inventory');
    let error=0,probes=0,worst=null;
    for(const slot of skeleton.slots){
      const attachment=slot.appliedPose.attachment,points=frame.vertices[slot.data.name];
      if(!attachment||!Number.isInteger(attachment.worldVerticesLength))throw Error('attachment_missing');
      const vertices=new Float32Array(attachment.worldVerticesLength);
      attachment.computeWorldVertices(skeleton,slot,0,vertices.length,vertices,0,2);
      if(vertices.length!==points.length*2)throw Error('vertex_inventory');
      for(let i=0;i<points.length;i++){
        const delta=Math.hypot(vertices[2*i]-points[i][0],vertices[2*i+1]-points[i][1]);
        if(!Number.isFinite(delta))throw Error('nonfinite_vertices');
        if(delta>error){error=delta;worst={slot:slot.data.name,vertex:i,expected:points[i],actual:[vertices[2*i],vertices[2*i+1]]};}
        probes++;
      }
    }
    if(error>.001){
      window.captureFailure={reason_code:'official_pose_mismatch',animation,index,time:frame.time,
        max_error_px:error,tolerance_px:.001,...worst};
      throw Error('official_pose_mismatch');
    }
    gl.viewport(0,0,canvas.width,canvas.height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
    renderer.begin();renderer.drawSkeleton(skeleton);renderer.end();
    gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
    if(gl.getError()!==gl.NO_ERROR)throw Error('framebuffer_read_failed');
    let visible=0,border=0;
    for(let y=0;y<canvas.height;y++)for(let x=0;x<canvas.width;x++)if(pixels[(y*canvas.width+x)*4+3]>=8){
      visible++;if(x===0||y===0||x===canvas.width-1||y===canvas.height-1)border++;
    }
    if(!visible||border)throw Error(!visible?'empty_framebuffer':'framebuffer_clipped');
    return {animation,index,time:frame.time,max_error_px:error,probes,visible_pixels:visible,border_pixels:border,
      draw_order:actualOrder,draw_order_matches:true};
  };
  window.framePNG=()=>canvas.toDataURL('image/png');window.ready=true;
})().catch(e=>{window.failure=String(e.stack||e);});
