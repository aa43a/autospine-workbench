/* Diagnostic only: actual texture alpha, original order, exact same-frame poses. */
window.inspectMaterialVisibility = async fixture => {
  const {width,height,left,bottom}=fixture.info;
  if(width*height>4194304)throw Error('visibility_camera_budget');
  const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
  const gl=canvas.getContext('webgl',{alpha:true,antialias:false,premultipliedAlpha:true,preserveDrawingBuffer:true});
  if(!gl)throw Error('visibility_webgl_missing');
  const atlas=new spine.TextureAtlas(fixture.atlas);
  await Promise.all(atlas.pages.map(async p=>{
    if(!fixture.textures[p.name])throw Error('visibility_texture_missing');
    const image=new Image();image.src=fixture.textures[p.name];await image.decode();
    p.setTexture(new spine.GLTexture(gl,image,false,false));
  }));
  const data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(fixture.skeleton);
  const renderer=new spine.SceneRenderer(canvas,gl);renderer.camera.setViewport(width,height);
  renderer.camera.position.x=left+width/2;renderer.camera.position.y=bottom+height/2;renderer.camera.update();
  function pose(time){
    const skeleton=new spine.Skeleton(data),state=new spine.AnimationState(new spine.AnimationStateData(data));
    skeleton.setupPose();state.setAnimation(0,'external-motion',false);state.update(time);state.apply(skeleton);
    skeleton.updateWorldTransform(spine.Physics.update);return skeleton;
  }
  const rows=[];
  for(const row of fixture.rows){
    const rig=pose(row.time),order=rig.drawOrder.appliedPose.map(s=>s.data.name);
    if(JSON.stringify(order)!==JSON.stringify(row.draw_order))throw Error('visibility_order_mismatch');
    const saved=rig.slots.map(s=>s.appliedPose.attachment);
    const x0=Math.min(...row.points.map(p=>p.x)),y0=Math.min(...row.points.map(p=>p.y));
    const rw=Math.max(...row.points.map(p=>p.x))-x0+1,rh=Math.max(...row.points.map(p=>p.y))-y0+1;
    function render(mode,name){
      rig.slots.forEach((s,i)=>{s.appliedPose.attachment=(mode==='only'&&s.data.name!==name||mode==='without'&&s.data.name===name)?null:saved[i];});
      gl.viewport(0,0,width,height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
      renderer.begin();renderer.drawSkeleton(rig);renderer.end();
      const bytes=new Uint8Array(rw*rh*4);gl.readPixels(x0,height-y0-rh,rw,rh,gl.RGBA,gl.UNSIGNED_BYTE,bytes);
      if(gl.getError()!==gl.NO_ERROR)throw Error('visibility_framebuffer_error');
      return row.points.map(p=>Array.from(bytes.slice(((rh-1-(p.y-y0))*rw+p.x-x0)*4,((rh-1-(p.y-y0))*rw+p.x-x0)*4+4)));
    }
    const full=render('full'),image=new Image();image.src=row.screenshot;await image.decode();
    if(image.width!==width||image.height!==height)throw Error('visibility_screenshot_size');
    const check=document.createElement('canvas');check.width=width;check.height=height;
    const ctx=check.getContext('2d');ctx.drawImage(image,0,0);
    const old=ctx.getImageData(x0,y0,rw,rh).data;let maximum=0;
    row.points.forEach((p,i)=>{
      const j=((p.y-y0)*rw+p.x-x0)*4,a=old[j+3];
      for(let c=0;c<4;c++)maximum=Math.max(maximum,Math.abs(full[i][c]-(c===3?a:Math.round(old[j+c]*a/255))));
    });
    if(fixture.whole_frame_trial){
      const original=ctx.getImageData(0,0,width,height).data,actual=new Uint8Array(width*height*4);
      gl.readPixels(0,0,width,height,gl.RGBA,gl.UNSIGNED_BYTE,actual);
      for(let y=0;y<height;y++)for(let x=0;x<width;x++){
        const a=(y*width+x)*4,b=((height-1-y)*width+x)*4,alpha=original[a+3];
        for(let c=0;c<4;c++)maximum=Math.max(maximum,Math.abs(actual[b+c]-(c===3?alpha:Math.round(original[a+c]*alpha/255))));
      }
    }
    if(maximum>1)throw Error('visibility_prior_frame_mismatch:'+maximum);
    const support=row.points.map(()=>[]);
    for(const name of (fixture.whole_frame_trial?[]:order)){
      const pixels=render('only',name);
      pixels.forEach((p,i)=>{if(p[3])support[i].push({slot:name,rgba:p});});
    }
    const drops={};
    for(const name of new Set(fixture.whole_frame_trial?[]:[row.region,row.body,...support.map(s=>s.at(-1)?.slot).filter(Boolean)])){
      const without=render('without',name);
      drops[name]=without.map((p,i)=>Math.max(...p.map((v,c)=>Math.abs(v-full[i][c]))));
    }
    const restored=render('full');
    if(JSON.stringify(restored)!==JSON.stringify(full))throw Error('visibility_restore_mismatch');
    const points=fixture.whole_frame_trial?[]:row.points.map((p,i)=>{
      const top=support[i].at(-1),opaque=top?.rgba[3]===255;
      const same=opaque&&top.rgba.every((v,c)=>Math.abs(v-full[i][c])<=1);
      return {...p,rgba:full[i],support:support[i],top_slot:top?.slot??null,
        opaque_top_matches_full:!!same,hide_deltas:Object.fromEntries(Object.entries(drops).map(([n,v])=>[n,v[i]]))};
    });
    let counterfactual=null;
    if(fixture.counterfactual){
      const after=fixture.counterfactual.after_slot,target=order.indexOf(row.region),end=order.indexOf(after);
      if(target<0||end<=target||after===row.body||end>=order.indexOf(row.body))throw Error('visibility_trial_order_invalid');
      const oldOrder=rig.drawOrder.appliedPose,trial=[...oldOrder],moving=trial.splice(target,1)[0];
      trial.splice(trial.findIndex(s=>s.data.name===after)+1,0,moving);
      const all=()=>{const bytes=new Uint8Array(width*height*4);gl.readPixels(0,0,width,height,gl.RGBA,gl.UNSIGNED_BYTE,bytes);
        if(gl.getError()!==gl.NO_ERROR)throw Error('visibility_trial_read_failed');return bytes;};
      const before=all(),beforePNG=row.capture_images===false?null:canvas.toDataURL('image/png');let moved,newPNG,changed=0,alphaChanged=0,maximum=0;
      const crossedVisibility=[];
      try{
        rig.drawOrder.appliedPose=trial;moved=render('full');const afterPixels=all();newPNG=row.capture_images===false?null:canvas.toDataURL('image/png');
        for(let i=0;i<before.length;i+=4){let delta=0;for(let c=0;c<4;c++)delta=Math.max(delta,Math.abs(before[i+c]-afterPixels[i+c]));
          if(delta>1)changed++;if(Math.abs(before[i+3]-afterPixels[i+3])>1)alphaChanged++;maximum=Math.max(maximum,delta);}
        for(const name of order.slice(target+1,end+1)){
          rig.drawOrder.appliedPose=oldOrder;render('without',name);const oldWithout=all();
          rig.drawOrder.appliedPose=trial;render('without',name);const newWithout=all();
          let oldVisible=0,newVisible=0,lost=0,gained=0,changedContribution=0;
          for(let i=0;i<before.length;i+=4){
            let a=0,b=0,d=0;
            for(let c=0;c<4;c++){
              a=Math.max(a,Math.abs(before[i+c]-oldWithout[i+c]));b=Math.max(b,Math.abs(afterPixels[i+c]-newWithout[i+c]));
              d=Math.max(d,Math.abs((before[i+c]-oldWithout[i+c])-(afterPixels[i+c]-newWithout[i+c])));
            }
            if(a>1)oldVisible++;if(b>1)newVisible++;if(a>1&&b<=1)lost++;if(a<=1&&b>1)gained++;if(d>1)changedContribution++;
          }
          crossedVisibility.push({slot:name,before_visible_pixels:oldVisible,after_visible_pixels:newVisible,
            lost_contribution_pixels:lost,gained_contribution_pixels:gained,changed_marginal_contribution_pixels:changedContribution,
            scope:'whole_frame_quantized_hide_delta_not_semantic_depth'});
        }
      }finally{rig.drawOrder.appliedPose=oldOrder;render('full');}
      if(!all().every((v,i)=>v===before[i]))throw Error('visibility_trial_restore_failed');
      counterfactual={after_slot:after,crossed_slots:order.slice(target+1,end+1),order:trial.map(s=>s.data.name),
        selected_pixel_changes:moved.filter((p,i)=>p.some((v,c)=>Math.abs(v-full[i][c])>1)).length,
        full_frame_changed_pixels:changed,full_frame_alpha_changes:alphaChanged,maximum_channel_delta:maximum,
        crossed_visibility:crossedVisibility,
        before_png:beforePNG,after_png:newPNG,restored_full_frame:true,selected:false};
    }
    rows.push({time:row.time,region:row.region,body:row.body,screenshot_sha256:row.screenshot_sha256,
      reference_scope:fixture.whole_frame_trial?'whole_frame':'selected_pixels',
      prior_frame_max_channel_delta:maximum,restored:true,points,...(counterfactual?{counterfactual}:{})});
    if(fixture.whole_frame_trial)console.log('visibility trial '+rows.length+'/'+fixture.rows.length);
  }
  const result={rows,context:gl.getContextAttributes(),scope:'selected_pixels_gpu_isolation_and_hide_delta_not_depth_correctness',authority:'none',selected:false};
  gl.getExtension('WEBGL_lose_context')?.loseContext();return result;
};
