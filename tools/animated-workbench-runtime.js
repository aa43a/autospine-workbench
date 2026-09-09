/* Opt-in numerical and framebuffer probe using the externally supplied official Runtime. */
(async () => {
  const get = async name => {const r = await fetch('/assets/' + name); if (!r.ok) throw Error('asset_fetch_failed'); return r.json();};
  const [json, manifest, playback] = await Promise.all(['skeleton.json', 'preview-manifest.json', 'playback.json'].map(get));
  const canvas = document.querySelector('canvas');
  const gl = canvas.getContext('webgl', {alpha:true, premultipliedAlpha:true, preserveDrawingBuffer:true});
  if (!gl) throw Error('webgl_unavailable');
  const renderer = new spine.SceneRenderer(canvas, gl);
  const atlasResponse = await fetch('/assets/skeleton.atlas');
  if (!atlasResponse.ok) throw Error('atlas_fetch_failed');
  const atlas = new spine.TextureAtlas(await atlasResponse.text());
  const textures = [];
  await Promise.all(atlas.pages.map(async page => {
    const image = new Image(); image.src = '/assets/' + page.name; await image.decode();
    if (!image.naturalWidth || !image.naturalHeight) throw Error('empty_texture');
    page.setTexture(new spine.GLTexture(gl, image, false, false));
    textures.push({name:page.name, width:image.naturalWidth, height:image.naturalHeight});
  }));
  const data = new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(json);
  const skeleton = new spine.Skeleton(data);
  const animation = manifest.animation;
  if (!data.findAnimation(animation)) throw Error('animation_missing');
  if (playback.fps !== 30 || playback.duration !== 2 || playback.frames.length !== 61) throw Error('playback_sampling_unsupported');
  function pose(time) {
    skeleton.setupPose();
    const state = new spine.AnimationState(new spine.AnimationStateData(data));
    state.setAnimation(0, animation, false); state.update(time); state.apply(skeleton);
    skeleton.updateWorldTransform(spine.Physics.update);
  }
  function vertices() {
    return skeleton.slots.map(slot => {
      const attachment = slot.appliedPose.attachment;
      if (!(attachment instanceof spine.MeshAttachment)) throw Error('non_mesh_attachment');
      const values = new Float32Array(attachment.worldVerticesLength);
      attachment.computeWorldVertices(skeleton, slot, 0, values.length, values, 0, 2);
      if (!values.every(Number.isFinite)) throw Error('nonfinite_world_vertices');
      return {id:slot.data.name, values:Array.from(values)};
    });
  }
  let left=Infinity, right=-Infinity, bottom=Infinity, top=-Infinity;
  for (const frame of playback.frames) for (const points of Object.values(frame.vertices)) for (const [x,y] of points) {
    if (![x,y].every(Number.isFinite)) throw Error('nonfinite_cpu_vertices');
    left=Math.min(left,x); right=Math.max(right,x); bottom=Math.min(bottom,-y); top=Math.max(top,-y);
  }
  if (!(right>left && top>bottom)) throw Error('empty_bounds');
  renderer.camera.setViewport((right-left)*1.2, (top-bottom)*1.2);
  renderer.resize(spine.ResizeMode.Fit);
  renderer.camera.position.x=(left+right)/2; renderer.camera.position.y=(bottom+top)/2; renderer.camera.update();
  function draw(time) {
    pose(time); gl.viewport(0,0,canvas.width,canvas.height); gl.clearColor(0,0,0,0); gl.clear(gl.COLOR_BUFFER_BIT);
    renderer.begin(); renderer.drawSkeleton(skeleton); renderer.end();
    const pixels = new Uint8Array(canvas.width*canvas.height*4);
    gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
    if (gl.getError() !== gl.NO_ERROR) throw Error('webgl_error');
    return pixels;
  }
  pose(0);
  let maxUV=0, maxSetup=0;
  const expected = new Map(manifest.regions.map(r=>[r.id,r]));
  for (const slot of skeleton.slots) {
    const a=slot.appliedPose.attachment, region=atlas.findRegion(a.path), out=new Float32Array(a.regionUVs.length);
    spine.MeshAttachment.computeUVs(region,a.regionUVs,out);
    const want=expected.get(slot.data.name)?.expected_page_uvs?.flat();
    if (!want || want.length !== out.length) throw Error('uv_shape_mismatch');
    out.forEach((v,i)=>{maxUV=Math.max(maxUV,Math.abs(v-want[i]));});
  }
  for (const row of vertices()) {
    const want=expected.get(row.id)?.setup_vertices_xy?.flatMap(([x,y])=>[x,-y]);
    if (!want || want.length !== row.values.length) throw Error('setup_shape_mismatch');
    row.values.forEach((v,i)=>{maxSetup=Math.max(maxSetup,Math.abs(v-want[i]));});
  }
  window.renderAnimatedAt = time => draw(time);
  window.verifyAnimated = () => {
    let initial=null, changed=false, maxMotion=0, outside=0, geometryChanged=false;
    const initialVertices=playback.frames[0].vertices, frames=[];
    for (let tick=0; tick<playback.frames.length; tick++) {
      const frame=playback.frames[tick];
      if (Math.abs(frame.time-tick/30)>1e-9) throw Error('frame_time_invalid');
      const pixels=draw(frame.time); let visible=0;
      for (let i=3;i<pixels.length;i+=4) if (pixels[i]) visible++;
      if (!initial) initial=pixels; else if (pixels.some((v,i)=>v!==initial[i])) changed=true;
      const actual=vertices();
      if (actual.length !== Object.keys(frame.vertices).length) throw Error('attachment_count_mismatch');
      for (const row of actual) {
        const want=frame.vertices[row.id]?.flatMap(([x,y])=>[x,-y]);
        const start=initialVertices[row.id]?.flatMap(([x,y])=>[x,-y]);
        if (!want || want.length !== row.values.length) throw Error('motion_shape_mismatch');
        row.values.forEach((v,i)=>{
          maxMotion=Math.max(maxMotion,Math.abs(v-want[i]));
          if (Math.abs(v-start[i])>.001) geometryChanged=true;
          const center=i%2?renderer.camera.position.y:renderer.camera.position.x;
          const extent=i%2?renderer.camera.viewportHeight:renderer.camera.viewportWidth;
          if (Math.abs(v-center)>extent/2) outside++;
        });
      }
      frames.push({tick,time:frame.time,visible_pixels:visible});
    }
    draw(0);
    return {animation,export_version:json.skeleton.spine,frames,textures:textures.sort((a,b)=>a.name.localeCompare(b.name)),
      max_page_uv_error:maxUV,max_setup_error_px:maxSetup,max_motion_error_px:maxMotion,
      outside_viewport_coordinates:outside,animation_changed:changed,geometry_changed:geometryChanged,
      camera:{x:renderer.camera.position.x,y:renderer.camera.position.y,width:renderer.camera.viewportWidth,height:renderer.camera.viewportHeight},
      passed:maxUV<=1e-6&&maxSetup<=.001&&maxMotion<=.001&&outside===0&&changed&&geometryChanged&&frames.every(f=>f.visible_pixels>0)};
  };
  draw(0); window.ready=true;
})().catch(error=>{window.failure=String(error.stack || error);});
