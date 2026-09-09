/** Linear vertex interpolation for diagnostic poses, not Spine runtime FK. */
export function sampleMeshTrack(frames, position) {
  const t = Math.max(0, Math.min(frames.length - 1, position));
  const index = Math.min(Math.floor(t), frames.length - 2), fraction = t - index;
  return frames[index].map((point, i) => point.map((v, axis) => v + (frames[index + 1][i][axis] - v) * fraction));
}

export function advanceMeshClock(position, direction, seconds, maximum = 8) {
  if (!(maximum > 0) || !Number.isFinite(seconds) || seconds < 0) throw new Error('invalid_mesh_clock');
  const phase = ((direction > 0 ? position : 2 * maximum - position) + seconds) % (2 * maximum);
  return {position: phase <= maximum ? phase : 2 * maximum - phase, direction: phase < maximum ? 1 : -1};
}

export function sampleFKTrack(model, track, position, corrected) {
  const t=Math.max(0,Math.min(8,position)), index=Math.min(7,Math.floor(t)), fraction=t-index;
  const angle=track.angles[index]+(track.angles[index+1]-track.angles[index])*fraction;
  const joint=model.bones.findIndex(b=>b.id===track.bone_id), pivot=model.bones[joint].head_xy;
  const rotate=(p,degrees)=>{const a=degrees*Math.PI/180;return [p[0]*Math.cos(a)-p[1]*Math.sin(a),p[0]*Math.sin(a)+p[1]*Math.cos(a)];};
  const frames=new Map(model.bones.map((bone,i)=>{
    const delta=rotate(bone.head_xy.map((v,k)=>v-pivot[k]),angle);
    return [bone.id,{head:i>=joint?delta.map((v,k)=>v+pivot[k]):bone.head_xy,angle:bone.world_rotation_degrees+(i>=joint?angle:0)}];
  }));
  const points=model.weights.map(row=>row.reduce((point,w)=>{
    const frame=frames.get(w.bone_id), p=rotate(w.local_xy,frame.angle);
    return point.map((v,k)=>v+w.weight*(frame.head[k]+p[k]));
  },[0,0]));
  if(corrected) points.forEach((p,i)=>p.forEach((_,k)=>{
    const a=track.corrected[index][i][k]-track.original[index][i][k];
    const b=track.corrected[index+1][i][k]-track.original[index+1][i][k];
    p[k]+=a+(b-a)*fraction;
  }));
  return points;
}

export function mountMeshTimeline(document, data, clock = globalThis) {
  const toolbar = document.createElement('section');
  toolbar.className = 'mesh-timeline';
  toolbar.innerHTML = '<button type="button" data-play>播放</button> <button type="button" data-reset>回到 Setup</button> '
    + '<label>速度 <select data-speed><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option></select></label>'
    + '<label>时间轴 <input data-time aria-label="网格预览时间轴" type="range" min="0" max="8" step="0.01" value="4"></label> <output data-time-label></output>'
    + `<p>每段 1 秒，端点往返播放；${data.some(m=>m.bones)?'逐帧骨骼 FK + 画布空间修正偏移插值，尚非 Spine Runtime。':'线性插值顶点用于诊断，不等同骨骼 FK 或 Spine 动画。'}</p>`;
  document.querySelector('main').before(toolbar);
  const slider = toolbar.querySelector('[data-time]'), play = toolbar.querySelector('[data-play]');
  let position = 4, direction = 1, playing = false, previous = null, request = null;
  const area = (points, t) => {const [a,b,c] = t.map(i => points[i]); return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);};
  const views = [...document.querySelectorAll('[data-mesh]')].map(section => {
    const model = data[Number(section.dataset.mesh)], svg = section.querySelector('svg');
    const joint = section.querySelector('[data-joint]'), variant = section.querySelector('[data-variant]');
    const polygons = model.triangles.map(() => {
      const node = document.createElementNS('http://www.w3.org/2000/svg', 'polygon'); svg.append(node); return node;
    });
    const edges = [...new Set(model.triangles.flatMap(t => t.map((a,i) => [a,t[(i+1)%3]].sort((a,b)=>a-b).join(','))))].map(e=>e.split(',').map(Number));
    const draw = () => {
      const track = model.tracks[Number(joint.value)], frames = variant?.value === 'corrected' ? track.corrected : track.original;
      const points = model.bones ? sampleFKTrack(model,track,position,variant?.value==='corrected') : sampleMeshTrack(frames, position);
      let inversions = 0, minimum = Infinity, maximum = -Infinity, stretch = 0;
      model.triangles.forEach((t, i) => {
        const ratio = area(points,t)/area(model.setup,t); minimum=Math.min(minimum,ratio); maximum=Math.max(maximum,ratio);
        if (ratio<=0) inversions++;
        polygons[i].setAttribute('points', t.map(v=>points[v].join(',')).join(' '));
        polygons[i].style.fill = ratio<=0 ? '#ff405acc' : ratio<.5||ratio>2 ? '#ffbd4588' : '#51b8d733';
      });
      edges.forEach(([a,b])=>{const dist=p=>Math.hypot(p[a][0]-p[b][0],p[a][1]-p[b][1]);stretch=Math.max(stretch,dist(points)/dist(model.setup));});
      const low=Math.min(7,Math.floor(position)), f=position-low;
      const angle=track.angles[low]+(track.angles[low+1]-track.angles[low])*f;
      section.querySelector('.qa').textContent=`${angle.toFixed(1)}° · 翻转 ${inversions} · 面积比 ${minimum.toFixed(3)}—${maximum.toFixed(3)} · 边长倍率 ${stretch.toFixed(3)}`;
    };
    joint.addEventListener('change',draw); variant?.addEventListener('change',draw);
    return draw;
  });
  const draw = () => {slider.value=String(position);toolbar.querySelector('[data-time-label]').textContent=`${position.toFixed(2)} / 8.00 秒`;views.forEach(v=>v());};
  const stop = () => {playing=false;previous=null;play.textContent='播放';if(request!==null)clock.cancelAnimationFrame(request);request=null;};
  const tick = now => {
    if(!playing)return;
    if(previous!==null)({position,direction}=advanceMeshClock(position,direction,Math.min(.1,(now-previous)/1000)*Number(toolbar.querySelector('[data-speed]').value)));
    previous=now;draw();request=clock.requestAnimationFrame(tick);
  };
  play.addEventListener('click',()=>{if(playing)stop();else{playing=true;play.textContent='暂停';request=clock.requestAnimationFrame(tick);}});
  slider.addEventListener('input',()=>{stop();position=Number(slider.value);draw();});
  toolbar.querySelector('[data-reset]').addEventListener('click',()=>{stop();position=4;direction=1;draw();});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
  draw();
}
