import {brushHitsTriangle, brushStrokePoints} from './sleeve-brush.js';
import {mountSleeveLive} from './sleeve-live-panel.js';

export function sleeveImageFrame(box) {
  if (!Array.isArray(box) || box.length !== 4 || !box.every(Number.isFinite) || box[2] <= box[0] || box[3] <= box[1])
    throw Error('图层边界无效');
  const [x,y,right,bottom] = box, width = right-x, height = bottom-y;
  return {x,y,width,height,viewBox:`${x-10} ${y-10} ${width+20} ${height+20}`};
}

export function mountSleeveReview(root, candidate, initial, images, bones, meshes=null) {
  const copy = x => JSON.parse(JSON.stringify(x));
  let draft = copy(initial), history = [], active = 0, painting = false;
  const roles = ['unknown', 'sleeve', 'cuff', 'hand', 'hanging_cloth'];
  const labels = ['不确定', '贴臂袖布', '袖口', '手', '宽袖垂布'];
  const colors = ['#aaa', '#40d9aa', '#ffe45a', '#f58faa', '#9f91ff'];
  const select = root.querySelector('#region'), role = root.querySelector('#role');
  const svg = root.querySelector('svg'), message = root.querySelector('#message');
  const brush = root.querySelector('#brush'), brushValue = root.querySelector('#brush-value');
  const live=mountSleeveLive(root,candidate,images,bones,meshes);
  let cursor, lastPoint=null, lastEvent=null, polygons=[];
  function setBrush(value) {
    brush.value=String(Math.max(4,Math.min(120,Number(value))));
    brushValue.textContent=`${brush.value} px`;
    if (lastEvent) locate(lastEvent);
  }
  brush.oninput=() => setBrush(brush.value);
  root.querySelector('#brush-smaller').onclick=() => setBrush(Number(brush.value)-4);
  root.querySelector('#brush-larger').onclick=() => setBrush(Number(brush.value)+4);
  root.addEventListener('keydown', e => {
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
    if (e.key==='[' || e.key===']') {setBrush(Number(brush.value)+(e.key==='[' ? -4 : 4));e.preventDefault();}
  });
  candidate.records.forEach((r, i) => select.add(new Option(`${r.layer_id} / ${r.component_id}`, i)));
  roles.forEach((r, i) => role.add(new Option(labels[i], r)));
  function remember() { history.push(copy(draft)); if (history.length > 30) history.shift(); }
  function node(name, attrs) {
    const n = document.createElementNS('http://www.w3.org/2000/svg', name);
    for (const [key, value] of Object.entries(attrs)) n.setAttribute(key, value);
    return n;
  }
  function status() {
    const items = draft.records.flatMap(r => r.assignments);
    message.textContent = `草稿：${items.filter(a => a.role !== 'unknown').length}/${items.length} 个三角形已填写；自动建议不等于人工确认。`;
    live.update(active,draft,initial);
  }
  function render() {
    painting=false;lastPoint=null;lastEvent=null;polygons=[];
    svg.replaceChildren(); const r = candidate.records[active];
    if (!r) { message.textContent = '没有支持的手臂区域'; return; }
    const image = images[r.layer_id], frame = sleeveImageFrame(image.bbox);
    svg.setAttribute('viewBox', frame.viewBox);
    svg.append(node('image', {href:image.url, x:frame.x, y:frame.y, width:frame.width, height:frame.height}));
    r.triangles.forEach((t, i) => {
      const assignment = draft.records[active].assignments[i];
      const n = node('polygon', {points: t.map(v => r.vertices_xy[v].join(',')).join(' '),
        fill: colors[roles.indexOf(assignment.role)], 'fill-opacity': '.35', stroke: '#ddd', 'stroke-width': '.5', 'data-triangle': i});
      const title = node('title', {}); title.textContent = `#${i} ${labels[roles.indexOf(assignment.role)]} · ${assignment.origin}`;
      n.append(title); svg.append(n);polygons.push(n);
    });
    for (const b of bones) {
      const g = node('g', {'pointer-events': 'none', opacity: r.bone_ids.includes(b.id) ? '1' : '.25'});
      g.append(node('line', {x1:b.head_xy[0], y1:b.head_xy[1], x2:b.tail_xy[0], y2:b.tail_xy[1], stroke:'#59cfff', 'stroke-width':'2'}));
      if (r.bone_ids.includes(b.id)) {
        const text = node('text', {x:b.head_xy[0], y:b.head_xy[1], fill:'#fff', 'font-size':'10'});
        text.textContent = b.id; g.append(text);
      }
      svg.append(g);
    }
    cursor=node('circle', {fill:'none',stroke:'#fff','stroke-width':'1.5','vector-effect':'non-scaling-stroke','pointer-events':'none',visibility:'hidden'});
    svg.append(cursor);status();
  }
  function locate(event) {
    if (!cursor || !svg.getScreenCTM()) return null;
    lastEvent=event;
    const inverse=svg.getScreenCTM().inverse(),p=new DOMPoint(event.clientX,event.clientY).matrixTransform(inverse);
    const radius=Number(brush.value)/2*Math.hypot(inverse.a,inverse.b);
    cursor.setAttribute('cx',p.x);cursor.setAttribute('cy',p.y);cursor.setAttribute('r',radius);cursor.setAttribute('visibility','visible');
    return {point:[p.x,p.y],radius};
  }
  function paint(event) {
    const position=locate(event),r=candidate.records[active];if (!position || !r) return;
    const samples=brushStrokePoints(lastPoint,position.point,position.radius);lastPoint=position.point;
    r.triangles.forEach((t,i) => {
      if (!samples.some(p => brushHitsTriangle(p,position.radius,t.map(v => r.vertices_xy[v])))) return;
      draft.records[active].assignments[i]={triangle_id:i,role:role.value,origin:'manual_edit'};
      polygons[i].setAttribute('fill',colors[roles.indexOf(role.value)]);
      polygons[i].querySelector('title').textContent=`#${i} ${labels[roles.indexOf(role.value)]} · manual_edit`;
    });status();
  }
  svg.addEventListener('pointerdown', e => { if (e.button !== 0) return; remember();lastPoint=null; painting=true; paint(e); e.preventDefault(); });
  svg.addEventListener('pointermove', e => { if (painting) paint(e); else locate(e); });
  function endStroke() {painting=false;lastPoint=null;}
  svg.addEventListener('pointerleave', () => {lastPoint=null;lastEvent=null;if(cursor)cursor.setAttribute('visibility','hidden');});
  window.addEventListener('pointerup', endStroke);
  window.addEventListener('blur', endStroke);
  svg.addEventListener('pointercancel', endStroke);
  select.onchange = () => {active=Number(select.value); render();};
  root.querySelector('#suggest').onclick = () => {
    remember(); candidate.records[active].suggestions.forEach((s,i) => {
      if (draft.records[active].assignments[i].origin === 'pending')
        draft.records[active].assignments[i] = {triangle_id:i, role:s.suggested_role, origin:'geometry_prefill'};
    }); render();
  };
  root.querySelector('#undo').onclick = () => { if (history.length) {draft=history.pop(); render();} };
  root.querySelector('#reset').onclick = () => {remember(); draft=copy(initial); render();};
  root.querySelector('#save').onclick = () => {
    const url=URL.createObjectURL(new Blob([JSON.stringify(draft,null,2)],{type:'application/json'}));
    const a=document.createElement('a');a.href=url;a.download=`sleeve-region-draft-${candidate.project_id}.json`;a.click();
    setTimeout(() => URL.revokeObjectURL(url),1000);
  };
  root.querySelector('#load').onchange = async e => {
    try {
      const file=e.target.files[0]; if (!file) return; if (file.size > 8*1024*1024) throw Error('文件过大');
      const value=JSON.parse(await file.text());
      for (const key of Object.keys(initial).filter(k => k !== 'records'))
        if (JSON.stringify(value[key]) !== JSON.stringify(initial[key])) throw Error('来源不匹配');
      if (Object.keys(value).sort().join() !== Object.keys(initial).sort().join() || value.records.length !== initial.records.length) throw Error('清单不匹配');
      value.records.forEach((r,i) => {
        const base=initial.records[i];
        if (Object.keys(r).sort().join() !== Object.keys(base).sort().join() || r.layer_id !== base.layer_id || r.component_id !== base.component_id || r.assignments.length !== base.assignments.length) throw Error('区域不匹配');
        r.assignments.forEach((a,j) => {
          if (Object.keys(a).sort().join() !== 'origin,role,triangle_id' || a.triangle_id !== j || !roles.includes(a.role) || !['pending','geometry_prefill','manual_edit'].includes(a.origin) || (a.origin === 'pending' && a.role !== 'unknown') || (a.origin === 'geometry_prefill' && a.role !== candidate.records[i].suggestions[j].suggested_role)) throw Error('归属无效');
        });
      }); remember();draft=copy(value);render();
    } catch (error) {message.textContent=`载入失败：${error.message}`;}
    e.target.value='';
  };
  setBrush(brush.value);render();
}
