/* Exact sleeve poses rendered by the external official Spine WebGL runtime. */
(async () => {
  const canvas = document.querySelector('canvas');
  const gl = canvas.getContext('webgl', {alpha:true, premultipliedAlpha:true, preserveDrawingBuffer:true, antialias:false});
  if (!gl) throw Error('webgl_unavailable');
  const get = async name => { const r=await fetch('/'+name); if(!r.ok)throw Error('asset_missing');return r.json(); };
  const doc=await get('skeleton.json'), reference=await get('numeric-reference.json'), contact=await get('contact.json');
  const atlas=new spine.TextureAtlas(await (await fetch('/skeleton.atlas')).text());
  await Promise.all(atlas.pages.map(async page => {
    const image=new Image();image.src='/'+page.name;await image.decode();
    page.setTexture(new spine.GLTexture(gl,image,false,false));
  }));
  const data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(doc);
  const skeleton=new spine.Skeleton(data), renderer=new spine.SceneRenderer(canvas,gl);
  let left=Infinity,bottom=Infinity,right=-Infinity,top=-Infinity;
  for(const frames of Object.values(reference.animations))for(const f of frames)for(const [x,y] of f.points){
    left=Math.min(left,x);right=Math.max(right,x);bottom=Math.min(bottom,y);top=Math.max(top,y);
  }
  left=Math.floor(left)-8;bottom=Math.floor(bottom)-8;right=Math.ceil(right)+8;top=Math.ceil(top)+8;
  canvas.width=right-left;canvas.height=top-bottom;
  if(canvas.width>4096||canvas.height>4096)throw Error('framebuffer_size_limit');
  renderer.camera.setViewport(canvas.width,canvas.height);
  renderer.camera.position.x=left+canvas.width/2;renderer.camera.position.y=bottom+canvas.height/2;renderer.camera.update();
  const pixels=new Uint8Array(canvas.width*canvas.height*4);
  const probes=contact.interfaces.flatMap((r,i)=>r.samples.map(s=>({edge:r.edge,u:s.u,interface:i})));
  const debug=gl.getExtension('WEBGL_debug_renderer_info');
  window.captureInfo={width:canvas.width,height:canvas.height,left,bottom,context:gl.getContextAttributes(),
    vendor:gl.getParameter(debug?debug.UNMASKED_VENDOR_WEBGL:gl.VENDOR),
    renderer:gl.getParameter(debug?debug.UNMASKED_RENDERER_WEBGL:gl.RENDERER),
    probe_count:probes.length,animations:Object.keys(reference.animations)};
  window.captureFrame=(animation,index)=>{
    const frame=reference.animations[animation]?.[index];if(!frame)throw Error('frame_missing');
    skeleton.setupPose();const state=new spine.AnimationState(new spine.AnimationStateData(data));
    state.setAnimation(0,animation,false);state.update(frame.time);state.apply(skeleton);skeleton.updateWorldTransform(spine.Physics.update);
    if(skeleton.slots.length!==1)throw Error('slot_inventory');
    const slot=skeleton.slots[0],attachment=slot.appliedPose.attachment,vertices=new Float32Array(attachment.worldVerticesLength);
    attachment.computeWorldVertices(skeleton,slot,0,vertices.length,vertices,0,2);
    if(vertices.length!==frame.points.length*2)throw Error('vertex_inventory');
    let error=0;
    for(let i=0;i<frame.points.length;i++)error=Math.max(error,Math.hypot(vertices[i*2]-frame.points[i][0],vertices[i*2+1]-frame.points[i][1]));
    if(!Number.isFinite(error)||error>.001)throw Error('official_pose_mismatch');
    gl.viewport(0,0,canvas.width,canvas.height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
    renderer.begin();renderer.drawSkeleton(skeleton);renderer.end();
    gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
    if(gl.getError()!==gl.NO_ERROR)throw Error('framebuffer_read_failed');
    let visible=0;for(let i=3;i<pixels.length;i+=4)visible+=pixels[i]>=8;
    if(!visible)throw Error('empty_framebuffer');
    const failures=[];let minimum=255;
    for(const p of probes){
      const [a,b]=p.edge,x=vertices[2*a]*(1-p.u)+vertices[2*b]*p.u,y=vertices[2*a+1]*(1-p.u)+vertices[2*b+1]*p.u;
      // Match source QA's floor(x), floor(-y) native pixel centers exactly.
      const px=Math.floor(x)-left,py=Math.ceil(y)-1-bottom;
      if(px<0||py<0||px>=canvas.width||py>=canvas.height)throw Error('probe_outside_framebuffer');
      const alpha=pixels[(py*canvas.width+px)*4+3];minimum=Math.min(minimum,alpha);
      if(alpha<8)failures.push({interface:p.interface,u:p.u,world_xy:[x,y],pixel_xy:[px,py],alpha});
    }
    return {animation,index,time:frame.time,max_error_px:error,visible_pixels:visible,tested_samples:probes.length,
      min_alpha:minimum,failed_samples:failures.length,failures};
  };
  window.framePNG=()=>canvas.toDataURL('image/png');window.ready=true;
})().catch(e=>{window.failure=String(e.stack||e);});
