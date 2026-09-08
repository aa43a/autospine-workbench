"""Self-contained, fixed-world-viewport raster and track inspection."""
import json


def render(report, visuals):
    payload = json.dumps(dict(report=report, visuals=visuals), ensure_ascii=False).replace('<', '\\u003c')
    return '''<!doctype html><meta charset="utf-8"><title>空白跨帧轨迹</title>
<style>body{font:17px system-ui;margin:28px;background:#f5f6f8;color:#182130}select,input{margin:10px}svg{width:100%;height:570px;background:white;border:1px solid #ccd}pre{white-space:pre-wrap}input{width:50%}</style>
<h1>新增空白跨帧复核</h1><p>蓝：driver　绿：follower　紫：重叠　红：当前新增空白　橙：所选轨迹。比较同一时刻的两版动画。</p>
<p>轨迹是 3px 邻域关联候选，不是已确认裂缝；分裂／合并不强行续接。此页没有采用操作。</p>
<label>附件关系<select id="relation"></select></label><label>轨迹<select id="track"></select></label>
<div><label>帧<input id="tick" type="range" min="0" max="60" value="0"></label><span id="time"></span><label>视野<select id="viewport"><option value="local">当前帧放大</option><option value="world">固定世界视野</option></select></label></div>
<svg id="scene" aria-label="附件栅格与世界坐标轨迹"></svg><p id="summary"></p><details><summary>坐标与关联证据</summary><pre id="detail"></pre></details>
<script>const data=PAYLOAD;
const select=document.querySelector('#relation'),track=document.querySelector('#track'),slider=document.querySelector('#tick'),scene=document.querySelector('#scene');
const ns='http://www.w3.org/2000/svg';
function element(name,attrs){const node=document.createElementNS(ns,name);for(const [k,v] of Object.entries(attrs))node.setAttribute(k,v);scene.append(node);return node;}
data.report.relations.forEach((r,i)=>select.add(new Option(r.driver+' → '+r.follower,i)));
function relationChanged(){track.replaceChildren(new Option('全部轨迹','all'));const r=data.report.relations[select.value];if(!r){document.querySelector('#summary').textContent=document.querySelector('#detail').textContent='没有接缝候选；不计为通过。';return;}
r.tracks.forEach(t=>track.add(new Option(t.id+' · '+t.start_frame+'–'+t.end_frame,t.id)));
if(r.tracks.length){track.value=r.tracks[0].id;slider.value=r.tracks[0].start_frame;}draw();}
function draw(){const r=data.report.relations[select.value];if(!r)return;const frames=data.visuals[select.value],f=frames[+slider.value],rect=f.rect;
const left=Math.min(...frames.map(v=>v.rect[0])),top=Math.min(...frames.map(v=>v.rect[1]));
const right=Math.max(...frames.map(v=>v.rect[0]+v.rect[2])),bottom=Math.max(...frames.map(v=>v.rect[1]+v.rect[3]));
scene.replaceChildren();scene.setAttribute('viewBox',(document.querySelector('#viewport').value==='local'?[rect[0]-2,rect[1]-2,rect[2]+4,rect[3]+4]:[left-2,top-2,right-left+4,bottom-top+4]).join(' '));
element('image',{x:rect[0],y:rect[1],width:rect[2],height:rect[3],href:f.image,style:'image-rendering:pixelated'});
const tracks=r.tracks.filter(t=>track.value==='all'||t.id===track.value);
for(const t of tracks){element('polyline',{points:t.components.map(c=>c.centroid[0]+','+(-c.centroid[1])).join(' '),fill:'none',stroke:'#f59b17','stroke-width':'.22'});
for(const c of t.components)element('circle',{cx:c.centroid[0],cy:-c.centroid[1],r:.25,fill:'#f59b17'});
for(const c of t.components.filter(c=>c.frame===+slider.value)){element('circle',{cx:c.centroid[0],cy:-c.centroid[1],r:1,fill:'none',stroke:'#111','stroke-width':'.2'});}}
document.querySelector('#time').textContent=slider.value+' / 60 · '+(+slider.value/30).toFixed(3)+' 秒';
document.querySelector('#summary').textContent='本关系共 '+r.pixel_samples+' 个跨帧像素样本，'+r.tracks.length+' 条候选轨迹；当前选择 '+tracks.length+' 条。所有轨迹尚未分类，短轨迹也不等于噪声。';
document.querySelector('#detail').textContent=JSON.stringify({pixel_samples:r.pixel_samples,tracks:tracks.map(t=>({id:t.id,start:t.start_frame,end:t.end_frame,observed_frames:t.observed_frames,max_area:t.max_area_px,current:t.components.filter(c=>c.frame===+slider.value)})),association_events:r.association_events},null,2);}
select.onchange=relationChanged;slider.oninput=draw;document.querySelector('#viewport').onchange=draw;track.onchange=()=>{const r=data.report.relations[select.value],t=r.tracks.find(t=>t.id===track.value);if(t)slider.value=t.start_frame;draw();};relationChanged();
</script>'''.replace('PAYLOAD', payload)
