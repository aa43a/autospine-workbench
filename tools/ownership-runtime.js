/* Official Runtime harness. Does not substitute its parser, FK, or renderer. */
(async()=>{
  const canvas=document.querySelector('canvas'),status=document.querySelector('#status');
  const gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:true,preserveDrawingBuffer:true});
  if(!gl)throw new Error('webgl_unavailable');
  const renderer=new spine.SceneRenderer(canvas,gl);
  const name=new URLSearchParams(location.search).get('character');
  if(!['alice','lingxian','crino'].includes(name))throw new Error('character_invalid');
  const base='/'+name+'/';
  const fetchJSON=async p=>{const r=await fetch(base+p);if(!r.ok)throw new Error('fetch_failed');return r.json();};
  const json=await fetchJSON('skeleton.json'),manifest=await fetchJSON('preview-manifest.json');
  const animationName=Object.keys(json.animations).find(n=>n!=='setup'),combined=animationName==='combined-pose-inspection';
  const animation=json.animations[animationName];
  const seam=animationName==='seam-translation-inspection';
  const remapped=animationName==='remapped-seam-inspection';
  const alphaSeam=['alpha-seam-inspection','continuous-anchor-inspection','seam-shape-inspection','seam-increment-inspection'].includes(animationName)||remapped;
  const continuous=animationName==='continuous-corrective-inspection'||seam||alphaSeam;
  const duration=Math.max(...Object.values(animation.bones).flatMap(b=>b.rotate.map(k=>k.time)));
  document.querySelector('#time').max=duration;
  if(combined)document.querySelector('aside').textContent='主关节与远端corrective的离散组合姿态；每0.5秒切换，使用stepped key，不代表连续动作或生产QA通过。残余仍未绑定。';
  if(continuous)document.querySelector('aside').textContent='30 FPS corrective候选动画，60 FPS采样验证；接缝仅为顶点邻近诊断，完整角色与生产QA尚未通过。残余仍未绑定。';
  if(seam)document.querySelector('aside').textContent='接缝平移约束实验，尚未采用；整只鞋保持刚性。约束失败仍为blocked，不能将可播放当作接缝通过。';
  if(alphaSeam){
    document.querySelector('aside').textContent='Alpha边界局部过渡候选：30 FPS bake / 60 FPS采样；接触对应尚待复核，完整角色与生产QA未通过。';
    const p=document.createElement('p');p.textContent='Alpha边界增距：'+((manifest.shape_qa||manifest.alpha_seam_qa).after.relations.map(r=>r.driver+' ↔ '+r.follower+' '+r.max_distance_growth_px.toFixed(3)+' px（'+r.status+'）').join('；')||'无对应关系');
    document.querySelector('aside').after(p);
  }
  if(remapped)document.querySelector('aside').textContent='局部冲突重配候选；只处理目标分歧超过2px的组，保留所有源边界点。叠加与验算仍用原对应，尚未采用或通过完整接缝验收。';
  if(remapped){
    const p=document.createElement('p'),r=manifest.raster_comparison;
    p.textContent='触发冲突组 '+manifest.alpha_seam_qa.remapping.changes.length+'；CPU走廊空白像素峰值（原局部过渡 → 重配）：'+
      (r.after.relations.map((a,i)=>a.follower+' '+r.before.relations[i].max_gap_pixels+' → '+a.max_gap_pixels).join('；')||'无对应');
    document.querySelector('aside').after(p);
  }
  if(continuous){
    const summary=document.createElement('p'),qa=manifest.bake_qa;
    summary.textContent='采样网格通过 '+Object.values(qa.regions).filter(r=>r.passed).length+'/'+Object.keys(qa.regions).length+
      '；接缝诊断：'+(qa.seam_proxy.map(s=>s.regions.join(' ↔ ')+' 增距 '+s.max_distance_growth_px.toFixed(2)+' px（'+s.status+'）').join('；')||'无邻近对应点')+
      '。未覆盖区域：'+(qa.unpaired_regions.join('、')||'无；边界覆盖仍待验证');
    document.querySelector('aside').after(summary);
  }
  const text=await (await fetch(base+'skeleton.atlas')).text();
  async function loadAtlas(text,padded=false){
    const atlas=new spine.TextureAtlas(text);
    await Promise.all(atlas.pages.map(async page=>{
      const image=new Image();image.src=base+page.name;await image.decode();
      let textureImage=image;
      if(padded){
        const padding=document.createElement('canvas');padding.width=image.width+4;padding.height=image.height+4;
        padding.getContext('2d').drawImage(image,2,2);textureImage=padding;
      }
      page.setTexture(new spine.GLTexture(gl,textureImage,false,false));
    }));return atlas;
  }
  const atlas=await loadAtlas(text);
  const attachments=json.skins[0].attachments;
  const referenceText=Object.keys(attachments).map(id=>{
    const a=attachments[id][id];return `editor/images/${id}.png\nsize: ${a.width+4},${a.height+4}\nfilter: Linear,Linear\npma: false\n${id}\nbounds: 2,2,${a.width},${a.height}\n`;
  }).join('\n');
  const reference=await loadAtlas(referenceText,true);
  function instance(atlas){
    const data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(json);
    return {skeleton:new spine.Skeleton(data),data};
  }
  const shared=instance(atlas),isolated=instance(reference);
  function pose(item,time){
    item.skeleton.setupPose();
    const state=new spine.AnimationState(new spine.AnimationStateData(item.data));
    state.setAnimation(0,animationName,false);state.update(time);state.apply(item.skeleton);
    item.skeleton.updateWorldTransform(spine.Physics.update);
  }
  function vertices(item){
    return item.skeleton.slots.map(slot=>{
      const attachment=slot.appliedPose.attachment,values=new Float32Array(attachment.worldVerticesLength);
      attachment.computeWorldVertices(item.skeleton,slot,0,values.length,values,0,2);
      if(!Array.from(values).every(Number.isFinite))throw new Error('nonfinite_world_vertices');
      return {id:slot.data.name,values:Array.from(values)};
    });
  }
  const bounds=[];
  const boundsTimes=combined||continuous?animation.bones[Object.keys(animation.bones)[0]].rotate.map(k=>k.time):[0];
  for(const time of boundsTimes){pose(shared,time);bounds.push(...vertices(shared).flatMap(r=>r.values));}
  pose(shared,0);
  const xs=bounds.filter((_,i)=>i%2===0),ys=bounds.filter((_,i)=>i%2===1);
  const left=Math.min(...xs),right=Math.max(...xs),bottom=Math.min(...ys),top=Math.max(...ys);
  renderer.camera.setViewport((right-left)*1.5,(top-bottom)*1.5);
  renderer.resize(spine.ResizeMode.Fit);
  renderer.camera.position.x=(left+right)/2;renderer.camera.position.y=(bottom+top)/2;renderer.camera.update();
  let contactOverlay=null,showContacts=null;
  if(alphaSeam){
    const wrapper=document.createElement('div');wrapper.style.position='relative';canvas.before(wrapper);wrapper.append(canvas);
    const overlay=document.createElement('canvas');overlay.width=canvas.width;overlay.height=canvas.height;
    Object.assign(overlay.style,{position:'absolute',left:'0',top:'0',pointerEvents:'none',background:'transparent'});
    wrapper.append(overlay);contactOverlay=overlay.getContext('2d');
    const label=document.createElement('label');showContacts=document.createElement('input');showContacts.type='checkbox';showContacts.checked=true;
    label.append(showContacts,document.createTextNode('显示 alpha 边界对应（候选）'));wrapper.before(label);
    showContacts.onchange=()=>window.renderAt(Number(document.querySelector('#time').value));
  }
  function drawContacts(item){
    if(!contactOverlay)return;const c=contactOverlay;c.clearRect(0,0,canvas.width,canvas.height);if(!showContacts.checked)return;
    const mesh=new Map(vertices(item).map(r=>[r.id,r.values])),qa=(manifest.shape_qa||manifest.alpha_seam_qa).after;
    const point=(name,index)=>{const s=qa.boundaries[name].samples[index],v=mesh.get(name);let x=0,y=0;
      s.triangle.forEach((i,k)=>{x+=v[i*2]*s.barycentric[k];y+=v[i*2+1]*s.barycentric[k];});
      return [(x-renderer.camera.position.x)/renderer.camera.viewportWidth*canvas.width+canvas.width/2,canvas.height/2-(y-renderer.camera.position.y)/renderer.camera.viewportHeight*canvas.height];};
    c.strokeStyle='#e84c19';c.fillStyle='#007eaa';c.lineWidth=1;
    for(const r of qa.relations)for(const pair of r.pairs){const a=point(r.driver,pair.driver_sample),b=point(r.follower,pair.follower_sample);
      c.beginPath();c.moveTo(...a);c.lineTo(...b);c.stroke();c.beginPath();c.arc(...a,1.5,0,Math.PI*2);c.fill();}
  }
  function draw(item,time){
    pose(item,time);gl.viewport(0,0,canvas.width,canvas.height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
    renderer.begin();renderer.drawSkeleton(item.skeleton);renderer.end();
    drawContacts(item);
    const pixels=new Uint8Array(canvas.width*canvas.height*4);gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
    if(gl.getError()!==gl.NO_ERROR)throw new Error('webgl_error');return pixels;
  }
  const expected=new Map(manifest.regions.map(r=>[r.id,r]));let maxUV=0,maxSetup=0;
  function expectedWorld(time){
    const frames=new Map(),tracks=animation.bones;
    const rotate=(x,y,a)=>{const c=Math.cos(a*Math.PI/180),s=Math.sin(a*Math.PI/180);return [x*c-y*s,x*s+y*c];};
    for(const bone of json.bones){
      let angle=0;const keys=tracks[bone.name]?.rotate;
      if(keys){let i=0;while(i+1<keys.length&&keys[i+1].time<=time)i++;const a=keys[i],b=keys[Math.min(i+1,keys.length-1)];const f=b.time===a.time||a.curve==='stepped'?0:(time-a.time)/(b.time-a.time);angle=a.value+(b.value-a.value)*f;}
      const parent=frames.get(bone.parent)||{x:0,y:0,a:0},offset=rotate(bone.x,bone.y,parent.a);
      frames.set(bone.name,{x:parent.x+offset[0],y:parent.y+offset[1],a:parent.a+bone.rotation+angle});
    }
    const result=new Map();
    for(const [id,slot] of Object.entries(attachments)){
      const data=slot[id].vertices,values=[];let i=0,offset=0;
      const deformKeys=animation.attachments?.default?.[id]?.[id]?.deform;let deform=[];
      if(deformKeys){let k=0;while(k+1<deformKeys.length&&deformKeys[k+1].time<=time)k++;
        const a=deformKeys[k],b=deformKeys[Math.min(k+1,deformKeys.length-1)];
        const f=a.curve==='stepped'||a.time===b.time?0:(time-a.time)/(b.time-a.time);
        deform=a.vertices.map((v,i)=>v+f*(b.vertices[i]-v));}
      while(i<data.length){const count=data[i++];let x=0,y=0;
        for(let j=0;j<count;j++){const [index,lx,ly,w]=data.slice(i,i+4);i+=4;const f=frames.get(json.bones[index].name),p=rotate(lx+(deform[offset++]||0),ly+(deform[offset++]||0),f.a);x+=(f.x+p[0])*w;y+=(f.y+p[1])*w;}
        values.push(x,y);
      }result.set(id,values);
    }return result;
  }
  for(const slot of shared.skeleton.slots){
    const a=slot.appliedPose.attachment,region=atlas.findRegion(a.path),uvs=new Float32Array(a.regionUVs.length);
    spine.MeshAttachment.computeUVs(region,a.regionUVs,uvs);
    const want=expected.get(slot.data.name).expected_page_uvs.flat();
    for(let i=0;i<want.length;i++)maxUV=Math.max(maxUV,Math.abs(want[i]-uvs[i]));
  }
  for(const row of vertices(shared)){
    const want=expected.get(row.id).setup_vertices_xy.flatMap(p=>[p[0],-p[1]]);
    row.values.forEach((v,i)=>maxSetup=Math.max(maxSetup,Math.abs(v-want[i])));
  }
  let playing=false,t=0,last=performance.now();
  window.renderAt=time=>{t=time;draw(shared,time);document.querySelector('#time').value=t;document.querySelector('#stamp').textContent=t.toFixed(2)+'s';};
  window.verifyFrames=()=>{
    playing=false;const frames=[];let initial=null,changed=false,maxMotion=0,outsideViewport=0;
    const fps=combined?4:60;
    for(let tick=0;tick<=duration*fps;tick++){
      const time=tick/fps,a=draw(shared,time),b=draw(isolated,time);let max=0,different=0,visible=0;
      for(let i=0;i<a.length;i++){const d=Math.abs(a[i]-b[i]);max=Math.max(max,d);if(d>1)different++;if(i%4===3&&a[i])visible++;}
      if(!initial)initial=a;else if(a.some((v,i)=>v!==initial[i]))changed=true;
      const want=expectedWorld(time);
      for(const row of vertices(shared))row.values.forEach((v,i)=>{
        maxMotion=Math.max(maxMotion,Math.abs(v-want.get(row.id)[i]));
        const center=i%2?renderer.camera.position.y:renderer.camera.position.x,extent=i%2?renderer.camera.viewportHeight:renderer.camera.viewportWidth;
        if(Math.abs(v-center)>extent/2)outsideViewport++;
      });
      frames.push({tick,time,max_channel_error:max,channels_over_one:different,visible_pixels:visible});
    }
    draw(shared,0);return {animation:animationName,max_page_uv_error:maxUV,max_setup_error_px:maxSetup,max_motion_error_px:maxMotion,outside_viewport_coordinates:outsideViewport,animation_changed:changed,frames};
  };
  document.querySelector('#time').oninput=e=>{playing=false;t=Number(e.target.value);window.renderAt(t);};
  document.querySelector('#play').onclick=()=>{playing=!playing;};
  function animate(now){if(playing){t=(t+(now-last)/1000)%duration;draw(shared,t);document.querySelector('#time').value=t;document.querySelector('#stamp').textContent=t.toFixed(2)+'s';}last=now;requestAnimationFrame(animate);}
  draw(shared,0);requestAnimationFrame(animate);status.textContent=`${name} · Spine Runtime 已载入 · ${manifest.regions.length} 个候选附件 · ${animationName}`;
  if(window.installLocalFramebuffer)window.installLocalFramebuffer({canvas,gl,renderer,shared,isolated,pose});
  window.ready=true;
})().catch(error=>{document.querySelector('#status').textContent=error.stack;window.failure=String(error.stack);});
