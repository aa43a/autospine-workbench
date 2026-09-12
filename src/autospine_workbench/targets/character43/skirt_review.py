"""Whole-character captured-frame timeline with setup-only skirt overlay."""
from html import escape
from hashlib import sha256
import json
import re
from ...resolved_project import canonical_sha256


def render(files, capture):
    trial = json.loads(files['skirt-trial.json'])
    if capture.get('bundle_sha256') != canonical_sha256({n: sha256(raw).hexdigest() for n, raw in files.items()}):
        raise ValueError('skirt_review_capture_source')
    if capture.get('authority') != 'none' or trial.get('authority') != 'none':
        raise ValueError('skirt_review_authority')
    info = capture['info']; width, height = info['width'], info['height']
    if any(type(v) is not int for v in (width, height, info['left'], info['bottom'])) or not 0 < min(width, height) <= max(width, height) <= 8192:
        raise ValueError('skirt_review_viewport')
    times = {(r['animation'], r['index']): r['time'] for r in capture['results']}
    frames = []
    for shot in capture['screenshots']:
        if not re.fullmatch(r'frames/[a-zA-Z0-9_-]+\.png', shot['file']):
            raise ValueError('skirt_review_frame_path')
        frames.append(dict(shot, time=times[shot['animation'], shot['index']]))
    if not frames: raise ValueError('skirt_review_frames_missing')
    overlay = []; summaries = []
    for failure in trial.get('blocked_layers', []):
        summaries.append(f'<li>{escape(failure["layer_id"])}：尚未生成裙装网格，原图保留；{escape(failure["reason_code"])}</li>')
    for row in trial['rows']:
        mesh = row['mesh']; ox, oy = row['origin']
        def point(p):
            return (ox+p[0]-info['left'], info['bottom']+height-oy+p[1])
        for chain, support in zip(mesh['helper_chains'], row['contact']['root_torso_support']):
            points = [point(p) for p in chain['points']]
            encoded = ' '.join(f'{x:.4f},{y:.4f}' for x, y in points)
            overlay.append(f'<polyline points="{encoded}" stroke="#66dbff"/>')
            x, y = points[0]
            overlay.append(f'<circle cx="{x:.4f}" cy="{y:.4f}" r="5" fill="{("#f7d76b" if support else "#ff607c")}"/>')
        x0, y = point((0, row['contact']['waist_y'])); x1, _ = point((mesh['coverage']['canvas_size'][0], row['contact']['waist_y']))
        overlay.append(f'<path d="M{x0:.4f} {y:.4f}H{x1:.4f}" stroke="#f7d76b" stroke-dasharray="8 5"/>')
        summaries.append(f'<li>{escape(row["layer_id"])}：{len(mesh["vertices"])} 顶点，'
            f'{mesh["coverage"]["alpha_components"]} 个透明轮廓连通域，'
            f'3 根部中 {sum(row["contact"]["root_torso_support"])} 个有上衣重叠支持；腰部待复核。</li>')
    data = json.dumps(frames, ensure_ascii=False).replace('<', '\\u003c')
    return (f'''<!doctype html><meta charset="utf-8"><title>裙装整角色候选复核</title>
<style>body{{margin:24px;background:#14212c;color:#eee;font:16px system-ui}}button,select,input{{font:inherit;margin:6px;padding:8px}}
header{{position:sticky;top:0;background:#14212c;z-index:2}}.stage{{position:relative;max-width:700px;margin:auto}}
img{{display:block;width:100%;background:repeating-conic-gradient(#35434e 0% 25%,#26333e 0% 50%) 0/20px 20px}}
svg{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}}#slider{{width:min(70vw,800px)}}a{{color:#7bd8ff}}</style>
<h1>裙装骨链与整角色动作候选</h1><p>官方 Runtime 已捕获帧，可拖动时间轴。保留原纹理、绘制顺序与人工决定；没有自动采用。</p>
<p>黄色虚线是腰部候选，蓝色是辅助骨链；黄色根点有上衣重叠，红色根点缺少该证据。叠加仅显示在 Setup 帧。</p>
<ul>{''.join(summaries)}</ul><p>本版使用小幅确定性摆动测试，不代表布料物理；连接、裙摆形状与腿部遮挡仍待验收。</p>
<header><select id="motion" aria-label="动作"></select><button id="play">播放</button>
<label><input type="checkbox" id="overlay" checked>显示 Setup 骨链</label><br>
<input id="slider" type="range" min="0" value="0" aria-label="已捕获帧时间轴"><output id="position"></output></header>
<div class="stage"><img id="frame" alt="官方 Runtime 整角色帧"><svg id="bones" viewBox="0 0 {width} {height}" fill="none" stroke-width="2">{''.join(overlay)}</svg></div>
<p><a href="../report.json">Runtime 报告</a> · <a href="../setup/index.html">Setup 源图对照</a></p>
<script id="frames" type="application/json">{data}</script>
<script>
const frames=JSON.parse(document.getElementById('frames').textContent),motion=document.getElementById('motion'),slider=document.getElementById('slider'),
image=document.getElementById('frame'),bones=document.getElementById('bones'),toggle=document.getElementById('overlay'),button=document.getElementById('play');
let rows=[],timer=null;const labels={{idle:'待机','wave-left':'左手挥动',walk:'行走'}};
for(const name of [...new Set(frames.map(f=>f.animation))]){{const option=document.createElement('option');option.value=name;option.textContent=labels[name]||name;motion.append(option);}}
function stop(){{clearTimeout(timer);timer=null;button.textContent='播放';}}
function show(){{const row=rows[Number(slider.value)];image.src='../'+row.file;bones.style.display=toggle.checked&&row.index===0?'block':'none';
document.getElementById('position').textContent=` ${{row.time.toFixed(3)}} 秒 · 原始帧 ${{row.index}}`;}}
function select(){{stop();rows=frames.filter(f=>f.animation===motion.value);slider.max=rows.length-1;slider.value=0;show();}}
function tick(){{const i=Number(slider.value),next=(i+1)%rows.length,delay=next?Math.max(20,(rows[next].time-rows[i].time)*1000):150;
timer=setTimeout(()=>{{slider.value=next;show();tick();}},delay);}}
button.onclick=()=>{{if(timer!==null)stop();else{{button.textContent='暂停';tick();}}}};
slider.oninput=()=>{{stop();show();}};motion.onchange=select;toggle.onchange=show;select();
</script>''').encode('utf-8')
