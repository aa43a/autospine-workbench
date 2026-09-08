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
    state.setAnimation(0,'distal-inspection',false);state.update(time);state.apply(item.skeleton);
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
  pose(shared,0);let bounds=vertices(shared).flatMap(r=>r.values);
  const xs=bounds.filter((_,i)=>i%2===0),ys=bounds.filter((_,i)=>i%2===1);
  const left=Math.min(...xs),right=Math.max(...xs),bottom=Math.min(...ys),top=Math.max(...ys);
  renderer.camera.setViewport((right-left)*1.5,(top-bottom)*1.5);
  renderer.resize(spine.ResizeMode.Fit);
  renderer.camera.position.x=(left+right)/2;renderer.camera.position.y=(bottom+top)/2;renderer.camera.update();
  function draw(item,time){
    pose(item,time);gl.viewport(0,0,canvas.width,canvas.height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
    renderer.begin();renderer.drawSkeleton(item.skeleton);renderer.end();
    const pixels=new Uint8Array(canvas.width*canvas.height*4);gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
    if(gl.getError()!==gl.NO_ERROR)throw new Error('webgl_error');return pixels;
  }
  const expected=new Map(manifest.regions.map(r=>[r.id,r]));let maxUV=0,maxSetup=0;
  function expectedWorld(time){
    const frames=new Map(),tracks=json.animations['distal-inspection'].bones;
    const rotate=(x,y,a)=>{const c=Math.cos(a*Math.PI/180),s=Math.sin(a*Math.PI/180);return [x*c-y*s,x*s+y*c];};
    for(const bone of json.bones){
      let angle=0;const keys=tracks[bone.name]?.rotate;
      if(keys){let i=0;while(i+1<keys.length&&keys[i+1].time<=time)i++;const a=keys[i],b=keys[Math.min(i+1,keys.length-1)];const f=b.time===a.time?0:(time-a.time)/(b.time-a.time);angle=a.value+(b.value-a.value)*f;}
      const parent=frames.get(bone.parent)||{x:0,y:0,a:0},offset=rotate(bone.x,bone.y,parent.a);
      frames.set(bone.name,{x:parent.x+offset[0],y:parent.y+offset[1],a:parent.a+bone.rotation+angle});
    }
    const result=new Map();
    for(const [id,slot] of Object.entries(attachments)){
      const data=slot[id].vertices,values=[];let i=0;
      while(i<data.length){const count=data[i++];let x=0,y=0;
        for(let j=0;j<count;j++){const [index,lx,ly,w]=data.slice(i,i+4);i+=4;const f=frames.get(json.bones[index].name),p=rotate(lx,ly,f.a);x+=(f.x+p[0])*w;y+=(f.y+p[1])*w;}
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
    for(let tick=0;tick<=120;tick++){
      const time=tick/60,a=draw(shared,time),b=draw(isolated,time);let max=0,different=0,visible=0;
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
    draw(shared,0);return {max_page_uv_error:maxUV,max_setup_error_px:maxSetup,max_motion_error_px:maxMotion,outside_viewport_coordinates:outsideViewport,animation_changed:changed,frames};
  };
  document.querySelector('#time').oninput=e=>{playing=false;t=Number(e.target.value);window.renderAt(t);};
  document.querySelector('#play').onclick=()=>{playing=!playing;};
  function animate(now){if(playing){t=(t+(now-last)/1000)%2;draw(shared,t);document.querySelector('#time').value=t;document.querySelector('#stamp').textContent=t.toFixed(2)+'s';}last=now;requestAnimationFrame(animate);}
  draw(shared,0);requestAnimationFrame(animate);status.textContent=`${name} · Spine Runtime 已载入 · ${manifest.regions.length} 个候选附件 · 可播放 distal-inspection`;
  window.ready=true;
})().catch(error=>{document.querySelector('#status').textContent=error.stack;window.failure=String(error.stack);});
