"""Standalone timeline for anchored source-skeleton projection comparisons."""
import json


def render(times, variants, constraints=(), metrics=None):
    payload = json.dumps(dict(times=times, variants=variants, constraints=constraints, metrics=metrics or {})).replace('<', '\\u003c')
    return '''<!doctype html><meta charset="utf-8"><title>分部位投影对照</title>
<style>body{background:#101923;color:#e7eff6;font:16px system-ui;margin:24px}canvas{width:100%;max-width:1200px;background:#182735}input{width:65%}button,select{padding:8px;margin:8px}</style>
<h1>共同肩／髋锚点投影对照</h1><p>左：原投影；右：实验投影。仅源骨架，不代表角色材质、接触或遮挡通过。原始三维深度保留；侧向符号尚未自动决定。</p>
<button id="play">播放</button><select id="variant"></select><input id="time" type="range" min="0" step="0.001" value="0"><span id="label"></span>
<p id="diagnostic"></p><canvas id="canvas" width="1200" height="650"></canvas>
<script>const data='''+payload+''';
const slider=document.getElementById('time'),select=document.getElementById('variant'),canvas=document.getElementById('canvas'),ctx=canvas.getContext('2d');
for(const name of Object.keys(data.variants).filter(n=>n!=='original')){const o=document.createElement('option');o.value=o.textContent=name;select.append(o);}
slider.max=data.times.at(-1);let playing=false,last=0;
const points=Object.values(data.variants).flatMap(frames=>frames.flatMap(f=>Object.values(f).flatMap(s=>[s.start,s.end])));
let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
for(const [x,y] of points){minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);}
const scale=Math.min(500/Math.max(1e-6,maxX-minX),540/Math.max(1e-6,maxY-minY));
function draw(){const t=Number(slider.value);let index=0;for(let i=1;i<data.times.length;i++)if(Math.abs(data.times[i]-t)<Math.abs(data.times[index]-t))index=i;
 ctx.clearRect(0,0,1200,650);ctx.font='18px system-ui';
 ['original',select.value].forEach((name,column)=>{ctx.fillStyle='white';ctx.fillText(name,30+column*600,30);
  const map=p=>[(p[0]-(minX+maxX)/2)*scale+300+column*600,(p[1]-(minY+maxY)/2)*scale+340];
  for(const [role,s] of Object.entries(data.variants[name][index])){ctx.strokeStyle=role.endsWith('.left')?'#ffb452':role.endsWith('.right')?'#63d2ef':'#aaa';ctx.lineWidth=4;ctx.beginPath();ctx.moveTo(...map(s.start));ctx.lineTo(...map(s.end));ctx.stroke();ctx.fillStyle=ctx.strokeStyle;ctx.beginPath();ctx.arc(...map(s.start),3,0,Math.PI*2);ctx.fill();}
 });document.getElementById('label').textContent=data.times[index].toFixed(3)+' 秒';
 const record=data.constraints.find(r=>r.variant===select.value),failures=record?.failures||[];
 const legs=(data.metrics[select.value]?.records||[]).filter(r=>r.group.startsWith('leg.'));
 const adjustments=record?.length_changes||[],blend=Math.max(0,...adjustments.map(r=>r.blend||0));
 document.getElementById('diagnostic').textContent=`不可达骨段采样：${failures.length}（不可达帧保留未约束投影，不算通过）。`+legs.map(r=>`${r.group} 新增脚踝位移/初始投影腿长：${(100*r.added_motion_over_initial_projected_chain).toFixed(2)}%`).join('；')+`。向源三维骨长调整的最大混合量：${(blend*100).toFixed(2)}%。保持源脚踝不等于真实脚底接触；膝分支尚未自动确定。`;
 for(const row of record?.source_relative_continuity?.records||[])document.getElementById('diagnostic').textContent+=` ${row.side} 相对源三维方向变化的最大额外帧间角度 ${row.maximum_excess_step_degrees.toFixed(3)}°（${row.time.toFixed(3)} 秒，仅幅度对照）。`;
 window.projectionState={frame:index,time:data.times[index],variant:select.value};}
function stop(){playing=false;document.getElementById('play').textContent='播放';}
slider.oninput=()=>{stop();draw();};select.onchange=draw;
document.getElementById('play').onclick=()=>{playing=!playing;last=performance.now();if(Number(slider.value)>=Number(slider.max))slider.value=0;document.getElementById('play').textContent=playing?'暂停':'播放';};
function tick(now){if(playing){slider.value=Math.min(Number(slider.max),Number(slider.value)+(now-last)/1000);draw();if(Number(slider.value)>=Number(slider.max))stop();}last=now;requestAnimationFrame(tick);}draw();requestAnimationFrame(tick);
</script>'''
