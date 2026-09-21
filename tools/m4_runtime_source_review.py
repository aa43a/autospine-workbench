"""Pair verified runtime screenshots with interpolated source limb observations."""
import argparse
from bisect import bisect_right
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.oblique_source import extract


def interpolate_source(times,vectors,time):
    if not times or time<times[0]-1e-6 or time>times[-1]+1e-6:
        raise ValueError('source_review_time_outside_source')
    i=max(0,min(len(times)-1,bisect_right(times,time)-1));j=min(i+1,len(times)-1)
    u=0 if i==j else max(0,min(1,(time-times[i])/(times[j]-times[i])))
    return {role:[a+(b-a)*u for a,b in zip(rows[i],rows[j])] for role,rows in vectors.items()}


def run(folder,source_folder):
    report=json.loads((folder/'report.json').read_bytes())
    source=json.loads((source_folder/'report.json').read_bytes())
    if report['source_candidate_sha256']!=source['candidate_bundle_sha256']:
        raise ValueError('source_review_parent_mismatch')
    AnimatedStore(folder/'isolated-store').read(report['candidate_bundle_sha256'])
    runtime=json.loads((folder/'runtime/report.json').read_bytes())
    if runtime['bundle_sha256']!=report['candidate_bundle_sha256']:
        raise ValueError('source_review_runtime_mismatch')
    identity=source['motion_identity']
    bundle=VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'],identity['bundle_sha256'])
    vectors,_,_=extract(bundle)
    keys=next(t for t in bundle.motion['tracks'] if t['property']=='rotation')['keys']
    times=[k['tick']/bundle.motion['ticks_per_second'] for k in keys]
    results={(r['animation'],r['index']):r for r in runtime['results']};frames=[]
    for shot in runtime['screenshots']:
        path=(folder/'runtime'/shot['file']).resolve()
        if not path.is_relative_to((folder/'runtime').resolve()) or sha256(path.read_bytes()).hexdigest()!=shot['sha256']:
            raise ValueError('source_review_screenshot_mismatch')
        row=results[(shot['animation'],shot['index'])]
        frames.append(dict(time=row['time'],image='runtime/'+shot['file'],source=interpolate_source(times,vectors,row['time'])))
    if not frames or any(b['time']<=a['time'] for a,b in zip(frames,frames[1:])):
        raise ValueError('source_review_frame_order')
    data=json.dumps(frames).replace('<','\\u003c')
    (folder/'source-review.html').write_text(HTML.replace('FRAME_DATA',data),encoding='utf-8')
    print(json.dumps(dict(captured_frames=len(frames),candidate=report['candidate_bundle_sha256'])))


HTML='''<!doctype html><meta charset="utf-8"><title>源方向与真实贴图</title>
<style>body{background:#15232e;color:white;font:16px sans-serif;margin:20px}button,select{padding:8px}input{width:45%}.panels{display:flex;gap:12px}img{width:55%;height:75vh;object-fit:contain;background:#263744}canvas{width:40%;height:600px}a{color:#7ce4ef}</style>
<h1>源方向与真实贴图：同步定位</h1><p>贴图为官方 Runtime 已捕获帧；不是逐帧实时渲染。源侧视仅表示选中肢体方向链，按源采样线性插值，不是完整三维角色。</p>
<button id="play">播放</button><input id="seek" type="range" min="0" value="0" step="1" aria-label="捕获帧"><span id="time"></span>
<select id="limb"><option value="leg.left">左腿</option><option value="leg.right">右腿</option><option value="arm.right">右臂</option><option value="arm.left">左臂</option></select>
<div class="panels"><img id="image" alt="实际捕获贴图"><canvas id="view" width="560" height="600"></canvas></div><p id="detail"></p><a href="report.json">候选报告</a>
<script>const frames=FRAME_DATA,seek=document.querySelector('#seek'),limb=document.querySelector('#limb'),ctx=document.querySelector('#view').getContext('2d');seek.max=frames.length-1;let playing=false,last=null,elapsed=0;
function draw(){const f=frames[+seek.value];document.querySelector('#image').src=f.image;document.querySelector('#time').textContent=f.time.toFixed(3)+' s · '+(+seek.value+1)+'/'+frames.length;ctx.clearRect(0,0,560,600);const [kind,side]=limb.value.split('.'),vs=['upper','lower'].map(p=>f.source['humanoid.'+kind+'.'+p+'.'+side]),s=110/vs.reduce((a,v)=>a+Math.hypot(...v),0);ctx.font='18px sans-serif';
for(const [label,axis,cy] of [['正面 X/Y',0,150],['侧面 深度/Y',2,450]]){ctx.fillStyle='white';ctx.fillText(label,20,cy-120);let x=280,y=cy;vs.forEach((v,i)=>{const nx=x+v[axis]*s,ny=y+v[1]*s;ctx.strokeStyle=i?'#fa87c8':'#71c9ff';ctx.lineWidth=4;ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(nx,ny);ctx.stroke();x=nx;y=ny;});}
document.querySelector('#detail').textContent=vs.map((v,i)=>`${i?'下段':'上段'}投影长度 ${(100*Math.hypot(v[0],v[1])/Math.hypot(...v)).toFixed(1)}%`).join(' · ')+'。侧视用于解释深度，不能代替目标遮挡验收。';}
seek.oninput=()=>{elapsed=frames[+seek.value].time;last=null;draw();};limb.onchange=draw;document.querySelector('#play').onclick=()=>{playing=!playing;last=null;document.querySelector('#play').textContent=playing?'暂停':'播放';};document.addEventListener('visibilitychange',()=>last=null);
function tick(now){if(playing&&last!==null&&!document.hidden){elapsed+=(now-last)/1000;if(elapsed>frames.at(-1).time)elapsed=frames[0].time;let i=0;while(i+1<frames.length&&frames[i+1].time<=elapsed)i++;if(+seek.value!==i){seek.value=i;draw();}}last=document.hidden?null:now;requestAnimationFrame(tick);}draw();requestAnimationFrame(tick);</script>'''

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);p.add_argument('source_folder',type=Path)
    a=p.parse_args();run(a.folder,a.source_folder)
