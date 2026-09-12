"""Build a scrubbable replay from verified official framebuffer screenshots."""
import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath


def frames(root):
    report = json.loads((root/'report.json').read_bytes())
    if report.get('passed') is not True or report.get('runtime_package') != '@esotericsoftware/spine-webgl':
        raise ValueError('official_capture_required')
    samples = {(r['animation'], r['index']): r['time'] for r in report['results']}
    rows = []
    for frame in report['screenshots']:
        path = PurePosixPath(frame['file'])
        if path.is_absolute() or '..' in path.parts or path.suffix != '.png' or '\\' in frame['file']:
            raise ValueError('capture_path_invalid')
        raw = (root/str(path)).read_bytes()
        if sha256(raw).hexdigest() != frame['sha256']:
            raise ValueError('capture_image_changed')
        rows.append(dict(file=frame['file'], time=samples[(frame['animation'], frame['index'])],
                         index=frame['index'], animation=frame['animation']))
    if len({r['animation'] for r in rows}) != 1 or len(rows) < 2:
        raise ValueError('single_animation_capture_required')
    rows.sort(key=lambda r: r['time'])
    if any(a['time'] >= b['time'] for a, b in zip(rows, rows[1:])):
        raise ValueError('capture_time_order')
    return rows


PAGE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>行走候选 · 时间轴复核</title>
<style>body{margin:0;background:#111b25;color:#edf4fa;font:16px system-ui}main{max-width:1100px;margin:auto;padding:16px}
h1{font-size:22px;margin:0 0 8px}p{color:#b7c8d7}.stage{height:65vh;background:repeating-conic-gradient(#2c3945 0% 25%,#25313c 0% 50%) 0/24px 24px;display:grid;place-items:center}
img{width:100%;height:100%;object-fit:contain;min-height:0}.controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:12px 0}
button,select{background:#224457;color:#fff;border:1px solid #4c7d94;border-radius:6px;padding:10px;font:inherit}input{width:100%;accent-color:#59c7eb}a{color:#79cff1}output{font-variant-numeric:tabular-nums}</style>
<main><h1>行走候选 · 时间轴复核</h1><p>官方 Runtime 实际截图采样回放。重点检查脚底滑动、身体起伏、手臂和服装连接。候选尚未采用。</p>
<div class="stage"><img id="image" alt="当前动画采样帧"></div>
<div class="controls"><button id="play">播放</button><button id="previous" aria-label="上一采样帧">上一帧</button><button id="next" aria-label="下一采样帧">下一帧</button>
<label>速度 <select id="speed"><option value="1">正常</option><option value="0.5">半速</option><option value="0.25">四分之一</option></select></label><output id="label"></output></div>
<input id="timeline" type="range" min="0" step="1" value="0" aria-label="动画时间轴">
<p>只播放本次捕获的采样画面；不会补帧或将末帧强行闭合成循环。<a href="report.json">官方报告</a></p></main>
<script id="data" type="application/json">__DATA__</script><script>
const rows=JSON.parse(document.getElementById('data').textContent),image=document.getElementById('image'),slider=document.getElementById('timeline'),label=document.getElementById('label'),play=document.getElementById('play'),speed=document.getElementById('speed');
let playing=false,index=0,elapsed=0,last=0;slider.max=rows.length-1;
for(const row of rows){const preload=new Image();preload.src=row.file;}
function show(i){index=i;slider.value=i;image.src=rows[i].file;label.textContent=`${rows[i].time.toFixed(3)} 秒 · 原始帧 ${rows[i].index} · ${i+1}/${rows.length} 张`;}
function pause(){playing=false;play.textContent='播放';}
function seek(i){pause();elapsed=rows[i].time;show(i);}
slider.oninput=()=>seek(Number(slider.value));document.getElementById('previous').onclick=()=>seek(Math.max(0,index-1));document.getElementById('next').onclick=()=>seek(Math.min(rows.length-1,index+1));
play.onclick=()=>{if(playing){pause();return;}if(index===rows.length-1){elapsed=0;show(0);}playing=true;last=performance.now();play.textContent='暂停';};
function tick(now){if(playing){elapsed+=(now-last)/1000*Number(speed.value);let i=index;while(i+1<rows.length&&rows[i+1].time<=elapsed)i++;if(i!==index)show(i);if(elapsed>=rows.at(-1).time)pause();}last=now;requestAnimationFrame(tick);}show(0);requestAnimationFrame(tick);
</script></html>'''


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    args = parser.parse_args()
    data = json.dumps(frames(args.capture), ensure_ascii=False).replace('<', '\\u003c')
    (args.capture/'timeline.html').write_text(PAGE.replace('__DATA__', data), encoding='utf-8')
