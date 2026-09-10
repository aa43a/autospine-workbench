"""Fixed-sample helper preview. No interpolation between unvalidated poses."""
import json
from html import escape


def render(doc):
    data=json.dumps(doc,ensure_ascii=True,allow_nan=False).replace('<','\\u003c')
    return '''<!doctype html><meta charset="utf-8"><title>垂布辅助骨候选</title>
<style>body{background:#152332;color:#eee;font:17px system-ui;margin:24px}section{display:inline-block;width:46%;vertical-align:top;padding:1%}svg{width:100%;height:65vh;background:#233447}button,select{padding:8px}nav{position:sticky;top:0;background:#152332;padding:12px}</style>
<h1>垂布辅助骨 · 前臂子骨</h1><p>新骨与手骨互为分支，手旋转不驱动垂布内部。共享边界、袖口接触和次级运动尚未解决；只播放33个固定样本，QA为每轨129点。</p>
<nav><button id="play">播放</button><button id="setup">Setup</button><input id="time" type="range" min="0" max="32" value="16" step="1"><span id="tick"></span></nav><main></main>
<script>
const doc='''+data+''';const rows=doc.records.filter(r=>r.tracks),main=document.querySelector('main'),slider=document.querySelector('#time');
const ns='http://www.w3.org/2000/svg';let running=false,last=0;
function node(tag,attrs={}){const n=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);return n;}
const views=rows.map(r=>{const s=document.createElement('section'),h=document.createElement('h2'),select=document.createElement('select'),qa=document.createElement('p'),svg=node('svg');
h.textContent=r.layer_id+' / '+r.component_id;
if(r.root_transition){const note=document.createElement('p');note.textContent=`根部过渡：${r.root_transition.selected?'保留候选':'回退'}；${r.root_transition.reason_codes.join(', ')}；试验失败 ${r.root_transition.baseline_failed_ticks.join('/')} → ${r.root_transition.trial_failed_ticks.join('/')}`;s.append(note);}
if(r.interface_root){const note=document.createElement('p'),a=r.interface_root;note.textContent=`交界根部：${a.selected?'保留候选':'保留旧根部'} · ${a.connected_components}段交界 · ${(a.reason_codes||[a.reason_code]).join(', ')}；${(a.baseline_failed_ticks||[]).join('/')} → ${(a.trial_failed_ticks||[]).join('/')}`;s.append(note);}
r.tracks.forEach((t,i)=>select.add(new Option(t.bone_id+' · '+t.failed_ticks+'/129 失败',i)));select.value='2';select.onchange=draw;
s.append(h,select,qa,svg);main.append(s);return {r,select,qa,svg};});
function draw(){const tick=Number(slider.value);document.querySelector('#tick').textContent='样本 '+tick+'/32';for(const {r,select,qa,svg} of views){
const track=r.tracks[Number(select.value)],frame=track.samples[tick];svg.replaceChildren();
const all=track.samples.flatMap(s=>s.points);const xs=all.map(p=>p[0]),ys=all.map(p=>p[1]);const x=Math.min(...xs)-10,y=Math.min(...ys)-10;
svg.setAttribute('viewBox',`${x} ${y} ${Math.max(...xs)-x+10} ${Math.max(...ys)-y+10}`);
const bad=new Set(track.qa[tick*4].bad_triangles);r.triangles.forEach((t,i)=>svg.append(node('polygon',{points:t.map(v=>frame.points[v].join(',')).join(' '),fill:bad.has(i)?'#e44a':'#55ccbb33',stroke:'#aaa','stroke-width':'.5'})));
for(const b of frame.bones){svg.append(node('line',{x1:b.head_xy[0],y1:b.head_xy[1],x2:b.tail_xy[0],y2:b.tail_xy[1],stroke:b.id===r.helper.id?'#fc5':'#5bf','stroke-width':'3'}));}
if(tick===16&&r.interface_root){for(const [a,b] of r.interface_root.edges){const p=r.setup_vertices[a],q=r.setup_vertices[b];svg.append(node('line',{x1:p[0],y1:p[1],x2:q[0],y2:q[1],stroke:'#ff79cb','stroke-width':'3'}));}const p=r.interface_root.root_xy;if(p)svg.append(node('circle',{cx:p[0],cy:p[1],r:5,fill:'#ff79cb'}));}
qa.textContent=`角度 ${frame.angle.toFixed(2)}° · 翻转 ${track.qa[tick*4].inversions} · setup误差 ${r.setup_error.toExponential(2)} px`;}}
slider.oninput=()=>{running=false;document.querySelector('#play').textContent='播放';draw();};document.querySelector('#setup').onclick=()=>{slider.value='16';slider.oninput();};
document.querySelector('#play').onclick=()=>{running=!running;document.querySelector('#play').textContent=running?'暂停':'播放';};
document.addEventListener('visibilitychange',()=>{if(document.hidden){running=false;document.querySelector('#play').textContent='播放';}});
function step(now){if(running&&now-last>100){slider.value=String((Number(slider.value)+1)%33);draw();last=now;}requestAnimationFrame(step);}draw();requestAnimationFrame(step);
</script>'''
