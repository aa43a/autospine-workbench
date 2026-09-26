/* Interactive inspection; immutable capture reports remain separate. */
(async () => {
  const el = id => document.getElementById(id), canvas = document.querySelector('canvas');
  const base = new URL('player-assets/', location.href);
  const asset = name => {
    if (!/^[A-Za-z0-9_./-]+$/.test(name) || name.split('/').some(p => !p || p === '.' || p === '..')) throw Error('asset_path');
    return new URL(name, base).href;
  };
  const get = async name => { const r = await fetch(asset(name)); if (!r.ok) throw Error(`读取 ${name} 失败 (${r.status})`); return r; };
  const runtimeReady = window.spine ? Promise.resolve() : new Promise((resolve,reject) => {
    const timer=setTimeout(()=>reject(Error('官方 Runtime 加载超时')),120000);
    el('runtime').addEventListener('load',()=>{clearTimeout(timer);resolve();},{once:true});
    el('runtime').addEventListener('error',()=>{clearTimeout(timer);reject(Error('官方 Runtime 加载失败'));},{once:true});
  });
  const [context] = await Promise.all([get('scene.json').then(r => r.json()), runtimeReady]);
  const doc=context.skeleton, atlasText=context.atlas;
  el('status').textContent='资源校验完成，正在创建动画预览…';
  const gl = canvas.getContext('webgl', {alpha:true, premultipliedAlpha:true, antialias:false});
  if (!gl) throw Error('当前浏览器无法创建 WebGL');
  const atlas = new spine.TextureAtlas(atlasText);
  const textureImages=new Map(),pixelTextures=new Map();let pixelTextureCount=0;
  await Promise.all(atlas.pages.map(async page => {
    if (!context.textures[page.name]) throw Error('图集纹理缺失');
    const image = new Image(); image.src = context.textures[page.name]; await image.decode();
    const texture=new spine.GLTexture(gl,image,false,false);page.setTexture(texture);
    textureImages.set(texture,{image,page});
  }));
  const data = new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(doc);
  const {width, height, left, bottom} = context.info;
  if (![width,height,left,bottom].every(Number.isFinite) || width < 1 || height < 1 || width > 4096 || height > 4096) throw Error('预览范围无效');
  canvas.width = width; canvas.height = height;
  const renderer = new spine.SceneRenderer(canvas, gl);
  renderer.camera.setViewport(width, height);
  renderer.camera.position.x = left + width/2; renderer.camera.position.y = bottom + height/2; renderer.camera.update();
  const names = {idle:'待机', walk:'行走', 'wave-left':'左手挥动', 'limb-flex-15':'肢体屈伸'};
  for (const animation of data.animations) {
    const option = document.createElement('option'); option.value = animation.name;
    option.textContent = `${names[animation.name] || animation.name} · ${animation.name}`; el('motion').append(option);
  }
  if (!data.animations.length) throw Error('候选没有动作');
  let time = 0, duration = 0, playing = false, previous = 0;
  let drawnSkeleton=null;
  const inspection=window.createCharacterInspection(context,renderer,()=>draw());
  for(const id of ['inspect-a','inspect-b']){
    for(const slot of doc.slots){
      const option=document.createElement('option');option.value=slot.name;option.textContent=slot.name;
      el(id).append(option);
    }
  }
  function inspect(){
    const regions=[el('inspect-a').value,el('inspect-b').value].filter(Boolean);
    inspection.setRegions(regions,el('inspect-mode').value);
    el('inspect-note').textContent=regions.length?'局部显示仅用于观察，不改变候选或代表遮挡验证通过。':'请先选择部件；当前显示完整角色。';
  }
  for(const id of ['inspect-a','inspect-b','inspect-mode'])el(id).onchange=inspect;
  el('inspect-clear').onclick=()=>{
    inspection.setTriangle(null);
    el('inspect-mode').value='full';el('inspect-a').value='';el('inspect-b').value='';inspect();
  };
  function draw() {
    // Reconstruct setup pose on every seek: reverse scrubbing never accumulates deform/state.
    const skeleton = new spine.Skeleton(data), state = new spine.AnimationState(new spine.AnimationStateData(data));
    skeleton.setupPose(); state.setAnimation(0, el('motion').value, false); state.update(time); state.apply(skeleton);
    skeleton.updateWorldTransform(spine.Physics.update);
    inspection.prepare(skeleton);
    gl.viewport(0,0,width,height); gl.clearColor(0,0,0,0); gl.clear(gl.COLOR_BUFFER_BIT);
    renderer.begin(); renderer.drawSkeleton(skeleton); inspection.draw(skeleton); renderer.end();
    drawnSkeleton=skeleton;
    if(window.characterPixelInspection&&el('pixel-check').checked)
      el('pixel-result').textContent='画面已改变，请重新点击检查。';
    window.characterPixelInspection=null;
    el('time').value = time; el('position').textContent = `${time.toFixed(3)} / ${duration.toFixed(3)} 秒`;
    window.characterPlayerState = {animation:el('motion').value, time, duration, playing};
  }
  function stop() { playing = false; el('play').textContent = '播放'; }
  function pixelTexture(texture){
    if(pixelTextures.has(texture))return pixelTextures.get(texture);
    const source=textureImages.get(texture);if(!source)throw Error('原纹理无法读取');
    const {image,page}=source;const count=image.width*image.height;
    if(pixelTextureCount+count>64_000_000)throw Error('纹理检查超过内存上限');
    const surface=document.createElement('canvas');surface.width=image.width;surface.height=image.height;
    const ctx=surface.getContext('2d',{willReadFrequently:true});if(!ctx)throw Error('无法读取纹理透明度');
    ctx.drawImage(image,0,0);const pixels=ctx.getImageData(0,0,image.width,image.height);
    const value={name:page.name,width:image.width,height:image.height,data:pixels.data,
      linear:page.minFilter===spine.TextureFilter.Linear&&page.magFilter===spine.TextureFilter.Linear,
      clamped:page.uWrap===spine.TextureWrap.ClampToEdge&&page.vWrap===spine.TextureWrap.ClampToEdge};
    pixelTextureCount+=count;pixelTextures.set(texture,value);return value;
  }
  el('pixel-check').onchange=()=>{
    window.characterPixelInspection=null;
    canvas.style.cursor=el('pixel-check').checked?'crosshair':'';
    el('pixel-result').textContent=el('pixel-check').checked?'点击画布检查；会暂停到当前时刻。':'像素检查已关闭。';
  };
  canvas.addEventListener('click',event=>{
    if(!el('pixel-check').checked)return;
    stop();draw();
    const panel=el('pixel-result');
    try{
      const view=window.characterInspectionState;
      if(view?.isolated||view?.hidden||view?.bone||window.characterTriangleInspection)
        throw Error('请先恢复完整角色并关闭骨骼/三角形高亮，再检查像素');
      const at=window.characterPixelMath.pixel([event.clientX,event.clientY],canvas.getBoundingClientRect(),width,height,renderer.camera);
      if(!at)return;
      if(gl.isContextLost())throw Error('画面上下文已丢失，请刷新恢复');
      const rgba=new Uint8Array(4);gl.readPixels(at.pixel[0],height-1-at.pixel[1],1,1,gl.RGBA,gl.UNSIGNED_BYTE,rgba);
      if(gl.getError()!==gl.NO_ERROR)throw Error('无法可靠读取当前画面');
      const evidence=window.inspectCharacterPixel(drawnSkeleton,at.world,pixelTexture);
      const result=window.characterPixelMath.classify(evidence.hits,rgba[3],evidence.limitations);
      const labels={transparent_texture:'理想采样仅有低透明度材质（合成上限低于 8/255）；没有证据支持靠调整顺序补足此点。',
        no_mesh:'按当前顶点计算，此点没有网格覆盖；请检查部件形状或素材缺口。',
        covered:'此点有可见材质。请结合下方来源和部件对照判断是否应当露出。',
        sampling_mismatch:'画面与理想纹理采样不一致，暂不能归因于绘制顺序。',
        unsupported:'当前渲染条件无法用这项检查判断顺序影响。'};
      panel.replaceChildren();
      const note=document.createElement('p');note.textContent=`${el('motion').value} · ${time.toFixed(6)} 秒 · 像素 ${at.pixel.join(', ')} · 画面透明度 ${rgba[3]}/255。${labels[result.kind]}`;panel.append(note);
      if(evidence.limitations.length){const warning=document.createElement('p');warning.textContent=evidence.limitations.join('；');panel.append(warning);}
      const grouped=new Map();for(const hit of evidence.hits){const old=grouped.get(hit.slot);if(!old||hit.alpha>old.alpha)grouped.set(hit.slot,hit);}
      for(const hit of [...grouped.values()].reverse()){
        const row=document.createElement('p');row.textContent=`${hit.slot} · 纹理透明度 ${hit.sourceAlpha.toFixed(2)}/255 `;
        const button=document.createElement('button');button.textContent='在部件对照中选择';
        button.onclick=()=>{el('inspect-a').value=hit.slot;el('inspect-b').value='';el('inspect-mode').value='full';inspect();};
        row.append(button);panel.append(row);
      }
      window.characterPixelInspection={artifact:context.artifact_sha256,animation:el('motion').value,time,
        ...at,framebuffer:Array.from(rgba),...evidence,...result,authority:'none',selected:false};
    }catch(error){panel.textContent=`检查未完成：${error.message}`;window.characterPixelInspection=null;}
  });
  function select() { stop(); time = 0; duration = data.findAnimation(el('motion').value).duration; el('time').max = duration; draw(); }
  el('play').onclick = () => { playing = !playing; if (playing && time >= duration) time = 0; previous = performance.now(); el('play').textContent = playing ? '暂停' : '播放'; draw(); };
  el('reset').onclick = () => { stop(); time = 0; draw(); };
  el('time').oninput = () => { stop(); time = Math.min(duration, Math.max(0, Number(el('time').value))); draw(); };
  el('motion').onchange = select;
  el('fullscreen').onclick = () => el('viewport').requestFullscreen?.().catch(() => { el('status').textContent = '当前浏览器不允许全屏，可继续在窗口播放。'; });
  document.addEventListener('visibilitychange', () => { if (document.hidden) { stop(); draw(); } });
  canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); stop(); window.characterPixelInspection=null; el('pixel-result').textContent='画面已失效，请刷新恢复。'; el('status').textContent = 'WebGL 上下文已丢失，请刷新恢复。'; });
  function tick(now) {
    if (playing) {
      // Missed display frames must not silently slow the source motion.
      time += Math.max(0, (now-previous)/1000) * Number(el('speed').value);
      if (time >= duration) { if (el('loop').checked && duration > 0) time %= duration; else { time = duration; stop(); } }
      draw();
    }
    previous = now; requestAnimationFrame(tick);
  }
  for (const id of ['motion','play','reset','time']) el(id).disabled = false;
  el('identity').textContent = `候选 ${context.artifact_sha256}`;
  el('status').textContent = '官方 Runtime 实时预览 · 选择动作或拖动时间轴';
  select();
  const requestedTime = Number(new URL(location.href).searchParams.get('time'));
  if (Number.isFinite(requestedTime)) { time = Math.min(duration, Math.max(0, requestedTime)); draw(); }
  const query=new URL(location.href).searchParams, requestedRegions=query.getAll('region');
  if(requestedRegions.length){
    if(requestedRegions.length<=2&&requestedRegions.every(n=>doc.slots.some(s=>s.name===n))){
      el('inspect-a').value=requestedRegions[0];el('inspect-b').value=requestedRegions[1]||'';
      el('inspect-mode').value=['full','isolate','hide'].includes(query.get('mode'))?query.get('mode'):'full';
      el('inspect-a').closest('details').open=true;inspect();
    }else{el('inspect-a').closest('details').open=true;el('inspect-note').textContent='定位部件与当前候选不匹配，已保留完整角色。';}
  }
  window.characterPlayerReady = true; requestAnimationFrame(tick);
  window.characterPlayerControl = {
    artifact: context.artifact_sha256,
    inspectRegions(regions,mode='isolate'){
      if(!inspection.setRegions(regions,mode))return false;
      inspection.setTriangle(null);return true;
    },
    inspectTriangle(slot,index,animation){
      if(animation!==el('motion').value)return false;
      return inspection.setTriangle(slot,index);
    },
    seek(value) {
      if (!Number.isFinite(value) || value < 0 || value > duration + 0.001) return false;
      stop(); time = Math.min(duration, value); draw(); return true;
    },
  };
})().catch(error => { document.getElementById('status').textContent = `预览加载失败：${error.message}`; window.characterPlayerError = String(error); });
