"""A scrub-able official captured-frame view for connected component mounts."""
from hashlib import sha256
from html import escape
import json
import re
from ...resolved_project import canonical_sha256


def render(files,capture):
    if capture.get('bundle_sha256')!=canonical_sha256({n:sha256(b).hexdigest() for n,b in files.items()}):
        raise ValueError('component_mount_capture_source')
    if capture.get('authority')!='none':raise ValueError('component_mount_capture_authority')
    mount=json.loads(files['component-mount.json']);times={(r['animation'],r['index']):r['time'] for r in capture['results']}
    frames=[]
    for shot in capture['screenshots']:
        if not re.fullmatch(r'frames/[A-Za-z0-9_-]+\.png',shot['file']):raise ValueError('component_mount_capture_path')
        frames.append(dict(animation=shot['animation'],time=times[shot['animation'],shot['index']],file='../'+shot['file']))
    if not frames:raise ValueError('component_mount_capture_empty')
    rows=''.join(f'<li>{escape(r["component_id"])} → {escape(r["proposed_parent"])} · {r["visible_pixels"]} 像素'
        f'{"（零散像素单独保留）" if r["component_id"]=="unbound-residual" else ""}</li>' for r in mount['parts'])
    data=json.dumps(frames,ensure_ascii=False).replace('<','\\u003c')
    return ('''<!doctype html><meta charset="utf-8"><title>分区绑定 · 整角色时间轴</title>
<style>body{margin:24px;background:#172330;color:#edf4fa;font:16px system-ui}main{display:flex;gap:24px;flex-wrap:wrap}
img{max-width:min(95vw,650px);max-height:78vh;background:repeating-conic-gradient(#34424e 0 25%,#263540 0 50%) 0/20px 20px}
nav{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:16px 0}input{width:min(60vw,600px)}button,select{padding:8px}</style>
<h1>分区绑定 · 整角色时间轴</h1><p>展示官方 Runtime 捕获帧，可拖动或按捕获时间播放。帧间不插值；连接和遮挡仍需视觉复核。</p>
<nav><select id="clip" aria-label="动作"></select><button id="play">播放</button><input id="time" type="range" min="0" step="1" value="0" aria-label="捕获帧时间轴"><output id="stamp"></output></nav>
<main><img id="frame" alt="整角色官方捕获帧"><aside><h2>分区归属</h2><ul>'''+rows+'''</ul><a href="../report.json">官方验证报告</a></aside></main>
<script>
const frames='''+data+''';const clip=document.getElementById('clip'),time=document.getElementById('time'),image=document.getElementById('frame'),stamp=document.getElementById('stamp'),play=document.getElementById('play');
let selected=[],playing=false,start=0;
for(const name of [...new Set(frames.map(r=>r.animation))]){const o=document.createElement('option');o.value=name;o.textContent=name;clip.append(o);}
function show(){const row=selected[Number(time.value)];image.src=row.file;stamp.textContent=row.time.toFixed(3)+' 秒 · '+(Number(time.value)+1)+' / '+selected.length;}
function stop(){playing=false;play.textContent='播放';}
function choose(){stop();selected=frames.filter(r=>r.animation===clip.value).sort((a,b)=>a.time-b.time);time.max=selected.length-1;time.value=0;show();}
function tick(now){if(!playing)return;const t=(now-start)/1000;let i=0;while(i+1<selected.length&&selected[i+1].time<=t)i++;time.value=i;show();if(i===selected.length-1){stop();return;}requestAnimationFrame(tick);}
clip.onchange=choose;time.oninput=()=>{stop();show();};play.onclick=()=>{if(playing){stop();return;}if(Number(time.value)===selected.length-1)time.value=0;playing=true;play.textContent='暂停';start=performance.now()-selected[Number(time.value)].time*1000;requestAnimationFrame(tick);};choose();
</script>''').encode()
