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
  await Promise.all(atlas.pages.map(async page => {
    if (!context.textures[page.name]) throw Error('图集纹理缺失');
    const image = new Image(); image.src = context.textures[page.name]; await image.decode();
    page.setTexture(new spine.GLTexture(gl, image, false, false));
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
    el('time').value = time; el('position').textContent = `${time.toFixed(3)} / ${duration.toFixed(3)} 秒`;
    window.characterPlayerState = {animation:el('motion').value, time, duration, playing};
  }
  function stop() { playing = false; el('play').textContent = '播放'; }
  function select() { stop(); time = 0; duration = data.findAnimation(el('motion').value).duration; el('time').max = duration; draw(); }
  el('play').onclick = () => { playing = !playing; if (playing && time >= duration) time = 0; previous = performance.now(); el('play').textContent = playing ? '暂停' : '播放'; draw(); };
  el('reset').onclick = () => { stop(); time = 0; draw(); };
  el('time').oninput = () => { stop(); time = Math.min(duration, Math.max(0, Number(el('time').value))); draw(); };
  el('motion').onchange = select;
  el('fullscreen').onclick = () => el('viewport').requestFullscreen?.().catch(() => { el('status').textContent = '当前浏览器不允许全屏，可继续在窗口播放。'; });
  document.addEventListener('visibilitychange', () => { if (document.hidden) { stop(); draw(); } });
  canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); stop(); el('status').textContent = 'WebGL 上下文已丢失，请刷新恢复。'; });
  function tick(now) {
    if (playing) {
      time += Math.min((now-previous)/1000, .1) * Number(el('speed').value);
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
  window.characterPlayerReady = true; requestAnimationFrame(tick);
  window.characterPlayerControl = {
    artifact: context.artifact_sha256,
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
