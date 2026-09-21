"""Synchronized skeletal experiment view; source panels show limb vectors only."""
import json


def render(frames, bones):
    data = json.dumps(dict(frames=frames, bones=bones)).replace('<', '\\u003c')
    return '''<!doctype html><meta charset="utf-8"><title>源姿态与投影对照</title>
<style>body{background:#15232e;color:white;font:16px sans-serif}canvas{background:#263744;width:100%;max-width:1400px}input{width:55%}button,select{padding:8px}</style>
<h1>源方向与投影长度对照</h1><p>左：原旋转重定向；中：实验拟合。右侧仅显示选定肢体的源方向链，不是完整角色或真实渲染。</p>
<p>尚未验证网格、接触和遮挡。朝向镜头时方向不可靠，长度缩短不等于视觉验收通过。</p>
<button id="play">播放</button><input id="seek" aria-label="时间" type="range" min="0" step="0.001"><span id="time"></span>
<select id="limb"><option value="arm.right">右臂</option><option value="arm.left">左臂</option><option value="leg.right">右腿</option><option value="leg.left">左腿</option></select>
<canvas id="view" width="1400" height="720"></canvas><p id="visibility"></p><a href="report.json">完整证据</a>
<script>const data=DATA,slider=document.querySelector('#seek'),canvas=document.querySelector('#view'),ctx=canvas.getContext('2d'),limb=document.querySelector('#limb');
const start=data.frames[0].time,end=data.frames.at(-1).time;slider.min=start;slider.max=end;slider.value=start;let playing=false,last=null;
let xmin=Infinity,xmax=-Infinity,ymin=Infinity,ymax=-Infinity;for(const f of data.frames)for(const key of ['before','after'])for(const p of Object.values(f[key])){xmin=Math.min(xmin,p[0]);xmax=Math.max(xmax,p[0]);ymin=Math.min(ymin,p[1]);ymax=Math.max(ymax,p[1]);}
const scale=Math.min(430/Math.max(1,xmax-xmin),620/Math.max(1,ymax-ymin));
function frameAt(t){let lo=0,hi=data.frames.length-1;while(lo<hi){const m=Math.ceil((lo+hi)/2);if(data.frames[m].time<=t)lo=m;else hi=m-1;}return data.frames[lo];}
function draw(){const f=frameAt(+slider.value);ctx.clearRect(0,0,1400,720);document.querySelector('#time').textContent=f.time.toFixed(3)+' s';ctx.font='16px sans-serif';
['before','after'].forEach((key,col)=>{const xy=p=>[col*480+240+(p[0]-(xmin+xmax)/2)*scale,360-(p[1]-(ymin+ymax)/2)*scale];ctx.fillStyle='white';ctx.fillText(col?'方向 + 长度候选':'原旋转基线',col*480+20,25);
for(const b of data.bones){if(!b.parent)continue;const a=xy(f[key][b.parent]),z=xy(f[key][b.name]);ctx.strokeStyle=col?'#62efb8':'#ffba70';ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...z);ctx.stroke();}});
const [kind,side]=limb.value.split('.'),vectors=['upper','lower'].map(part=>f.source['humanoid.'+kind+'.'+part+'.'+side]);
const length=vectors.reduce((s,v)=>s+Math.hypot(...v),0),s=170/length;
[['正面 X/Y',0,190],['侧面 深度/Y',2,490]].forEach(([label,axis,cy])=>{ctx.fillStyle='white';ctx.fillText(label,990,cy-110);let x=1120,y=cy;
vectors.forEach((v,i)=>{const nx=x+v[axis]*s,ny=y+v[1]*s;ctx.strokeStyle=i?'#fa87c8':'#71c9ff';ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(nx,ny);ctx.stroke();ctx.beginPath();ctx.arc(nx,ny,4,0,7);ctx.fill();x=nx;y=ny;});ctx.lineWidth=1;});
document.querySelector('#visibility').textContent=vectors.map((v,i)=>`${i?'下段':'上段'}投影长度 ${(100*Math.hypot(v[0],v[1])/Math.hypot(...v)).toFixed(1)}%`).join(' · ');}
slider.oninput=()=>{last=null;draw();};limb.onchange=draw;document.querySelector('#play').onclick=()=>{playing=!playing;last=null;document.querySelector('#play').textContent=playing?'暂停':'播放';};
document.addEventListener('visibilitychange',()=>last=null);
function tick(now){if(playing&&last!==null&&!document.hidden){let t=+slider.value+(now-last)/1000;if(t>end)t=start+(t-start)%(end-start);slider.value=t;draw();}last=document.hidden?null:now;requestAnimationFrame(tick);}draw();requestAnimationFrame(tick);</script>'''.replace('DATA', data)
