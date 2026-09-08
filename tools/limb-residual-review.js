/* Opt-in UI/capture hook. Asset bytes, tracks, weights and persistent decisions are untouched. */
window.installLocalFramebuffer=async({canvas,gl,renderer,shared,pose})=>{
  try{
    const character=new URLSearchParams(location.search).get('character');
    const manifest=await (await fetch('/'+character+'/preview-manifest.json')).json();
    if(manifest.schema!=='autospine.wing-limb-preview/v1')throw Error('residual_review_profile');
    const slots=new Set(shared.skeleton.slots.map(s=>s.data.name));
    const groups=manifest.context_layers.filter(r=>r.representation==='limb_candidates_with_unreviewed_residual_context')
      .map(r=>({id:r.layer_id,name:r.name,residual:r.attachments.filter(n=>n.startsWith('context-')),source_pixels:r.residual_visible_pixels}));
    if(!groups.length||groups.some(g=>g.residual.length!==1||!slots.has(g.residual[0])))throw Error('residual_review_inventory');
    const residuals=new Set(groups.flatMap(g=>g.residual));
    const modes=['full','without-all','residual-only',...groups.map(g=>'without:'+g.id)];
    function draw(time,mode){
      if(!Number.isFinite(time)||time<0||time>2||!modes.includes(mode))throw Error('residual_review_selection');
      pose(shared,time);
      const removed=mode.startsWith('without:')?new Set(groups.find(g=>'without:'+g.id===mode).residual):residuals;
      for(const slot of shared.skeleton.slots){
        const name=slot.data.name;
        if((mode==='residual-only'&&!residuals.has(name))||
           ((mode==='without-all'||mode.startsWith('without:'))&&removed.has(name)))slot.appliedPose.attachment=null;
      }
      gl.viewport(0,0,canvas.width,canvas.height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
      renderer.begin();renderer.drawSkeleton(shared.skeleton);renderer.end();
      const pixels=new Uint8Array(canvas.width*canvas.height*4);
      gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
      if(gl.getError()!==gl.NO_ERROR)throw Error('residual_framebuffer_error');
      return pixels;
    }
    function png(pixels){
      const out=document.createElement('canvas');out.width=canvas.width;out.height=canvas.height;
      const ctx=out.getContext('2d'),image=ctx.createImageData(out.width,out.height);
      for(let y=0;y<out.height;y++)for(let x=0;x<out.width;x++){
        const i=(y*out.width+x)*4,j=((out.height-1-y)*out.width+x)*4,a=pixels[j+3];
        for(let c=0;c<3;c++)image.data[i+c]=a?Math.min(255,Math.round(pixels[j+c]*255/a)):0;
        image.data[i+3]=a;
      }
      ctx.putImageData(image,0,0);return out.toDataURL('image/png');
    }
    window.residualReview={groups,modes,render(time,mode){return png(draw(time,mode));},
      locate(time,id){
        const group=groups.find(g=>g.id===id);if(!group)throw Error('residual_group_missing');
        const full=draw(time,'full'),fullImage=png(full),without=draw(time,'without:'+id),withoutImage=png(without);
        const targets=[];
        for(let i=0;i<full.length;i+=4){
          const delta=Math.max(...[0,1,2,3].map(c=>Math.abs(full[i+c]-without[i+c])));
          const exposed=full[i+3]>=8&&without[i+3]<8;
          if(delta>1||exposed)targets.push({pixel:[(i/4)%canvas.width,Math.floor(i/4/canvas.width)],delta,exposed});
        }
        draw(time,'full');
        const slot=shared.skeleton.slots.find(s=>s.data.name===group.residual[0]),attachment=slot.appliedPose.attachment;
        const vertices=new Float32Array(attachment.worldVerticesLength);
        attachment.computeWorldVertices(shared.skeleton,slot,0,attachment.worldVerticesLength,vertices,0,2);
        return {id,time,targets,world_vertices:Array.from(vertices),uvs:Array.from(attachment.regionUVs),
          triangles:Array.from(attachment.triangles),full_image:fullImage,without_image:withoutImage};
      },
      measure(time){
        const full=draw(time,'full');
        try{return {time,groups:groups.map(g=>({id:g.id,...limbResidualMetrics(full,draw(time,'without:'+g.id),canvas.width,canvas.height)}))};}
        finally{draw(time,'full');}
      },
      restoreCheck(time){
        const before=draw(time,'full');draw(time,'without-all');draw(time,'residual-only');const after=draw(time,'full');
        return before.every((v,i)=>v===after[i]);
      },
      camera:{width:canvas.width,height:canvas.height,world_center:[renderer.camera.position.x,renderer.camera.position.y],
        world_size:[renderer.camera.viewportWidth,renderer.camera.viewportHeight],rect_origin:'framebuffer_bottom_left'}};
    for(const id of ['play','time','stamp'])document.getElementById(id).hidden=true;
    const panel=document.createElement('section'),mode=document.createElement('select'),slider=document.createElement('input'),stamp=document.createElement('output');
    const labels=['完整合成','临时隐藏全部残余','仅显示残余',...groups.map(g=>'临时隐藏：'+g.name)];
    modes.forEach((m,i)=>mode.add(new Option(labels[i],m)));slider.type='range';slider.min=0;slider.max=2;slider.step=1/60;slider.value=0;
    const update=()=>{draw(Number(slider.value),mode.value);stamp.textContent=Number(slider.value).toFixed(3)+'s';};
    mode.onchange=slider.oninput=update;panel.append(mode,slider,stamp);canvas.before(panel);
    const background=document.createElement('select');
    for(const [label,value] of [['白底','#fff'],['深色背景','#172033'],['透明棋盘','repeating-conic-gradient(#ddd 0% 25%, #999 0% 50%) 0 0 / 20px 20px']])background.add(new Option(label,value));
    background.onchange=()=>{canvas.style.background=background.value;};panel.append(background);
    for(const time of [0,.5,1,1.5,2]){const b=document.createElement('button');b.textContent=time+'s';b.onclick=()=>{slider.value=time;update();};panel.append(b);}
    document.querySelector('h1').textContent='四肢残余 · 同帧显隐复核';
    document.querySelector('aside').textContent='仅临时改变显示，不删除像素或确认绑定。隐藏后出现透明区域只能说明原画面依赖残余，不能直接认定原动画有裂缝。拖动时间检查袖口、裙摆与鞋口。';
    update();window.residualReady=true;
  }catch(error){window.failure=String(error.stack);}
};
