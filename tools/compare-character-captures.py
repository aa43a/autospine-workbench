"""Build a draggable, exact-time comparison from verified official capture PNGs."""
import argparse
from html import escape
from hashlib import sha256
import json
from pathlib import Path


def load(root, expected, animation):
    raw = (root/'report.json').read_bytes(); report = json.loads(raw)
    if report.get('bundle_sha256') != expected or not report.get('passed') or report.get('runtime_package') != '@esotericsoftware/spine-webgl':
        raise ValueError('capture_comparison_source_mismatch')
    results = {(r['animation'], r['index']): r for r in report['results']}
    frames = {}
    for screenshot in report['screenshots']:
        if screenshot['animation'] != animation: continue
        path = (root/screenshot['file']).resolve()
        if not path.is_relative_to(root.resolve()): raise ValueError('capture_comparison_path')
        image = path.read_bytes()
        if sha256(image).hexdigest() != screenshot['sha256']: raise ValueError('capture_comparison_image_identity')
        time = results[animation, screenshot['index']]['time']
        frames[time] = (image, screenshot['sha256'])
    return report, frames, sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--before-character', required=True)
    parser.add_argument('--after-character', required=True)
    parser.add_argument('--animation', default='wave-left')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--title', default='角色动画 · 同帧对照')
    parser.add_argument('--after-label', default='修正候选')
    args = parser.parse_args()
    before, a, ash = load(args.before, args.before_character, args.animation)
    after, b, bsh = load(args.after, args.after_character, args.animation)
    for key in ('runtime_sha256', 'harness_sha256', 'browser_sha256'):
        if before[key] != after[key]: raise ValueError('capture_comparison_environment_mismatch')
    for key in ('width', 'height', 'left', 'bottom'):
        if before['info'][key] != after['info'][key]: raise ValueError('capture_comparison_camera_mismatch')
    times = sorted(set(a) & set(b))
    if len(times) < 2: raise ValueError('capture_comparison_matching_frames_missing')
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, time in enumerate(times):
        for prefix, frames in [('before', a), ('after', b)]:
            (args.output/f'{prefix}-{i}.png').write_bytes(frames[time][0])
        rows.append(dict(time=time, before=f'before-{i}.png', after=f'after-{i}.png',
                         before_sha256=a[time][1], after_sha256=b[time][1]))
    evidence = dict(authority='none', selected=False, animation=args.animation, frames=rows,
                    before_character_sha256=args.before_character, after_character_sha256=args.after_character,
                    before_report_sha256=ash, after_report_sha256=bsh,
                    scope='exact_time_same_camera_official_capture_png_comparison_not_visual_acceptance')
    (args.output/'comparison.json').write_text(json.dumps(evidence, indent=2)+'\n', encoding='utf-8')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TITLE</title><style>body{margin:0;background:#17222e;color:#edf5ff;font:16px system-ui;padding:24px}
header{position:sticky;top:0;background:#17222ef5;padding:12px;z-index:1}button{padding:8px 18px;background:#285472;color:white;border:1px solid #6d9bb7;border-radius:6px}
input{width:min(60vw,650px)}main{display:grid;grid-template-columns:1fr 1fr;gap:18px;max-width:1500px}figure{margin:0}
img{width:100%;background:repeating-conic-gradient(#34424e 0% 25%,#263540 0% 50%) 0/24px 24px}a{color:#8dddff}
@media(max-width:650px){main{grid-template-columns:1fr}}</style><header><h1>TITLE</h1>
<p>左侧原候选，右侧修正候选。两侧使用同一时刻、相机和官方渲染环境。</p>
<p>这是离散捕获帧对照；候选尚未采用，也不代表整角色视觉验收。</p>
<button id="play">播放</button> <input id="time" type="range" min="0" step="1" aria-label="选择捕获帧"> <output id="label"></output>
<a href="comparison.json">来源与帧记录</a></header><main><figure><h2>原候选</h2><img id="before" alt="原候选同帧捕获"></figure>
<figure><h2>AFTER_LABEL</h2><img id="after" alt="修正候选同帧捕获"></figure></main><script>
const frames=DATA;const slider=document.querySelector('#time'),label=document.querySelector('#label'),play=document.querySelector('#play');
slider.max=frames.length-1;slider.value=0;let timer=null;
function show(){const frame=frames[Number(slider.value)];document.querySelector('#before').src=frame.before;document.querySelector('#after').src=frame.after;label.textContent=frame.time.toFixed(3)+' 秒 · '+(Number(slider.value)+1)+'/'+frames.length;}
slider.addEventListener('input',show);play.addEventListener('click',()=>{if(timer){clearInterval(timer);timer=null;play.textContent='播放';return;}play.textContent='暂停';timer=setInterval(()=>{slider.value=(Number(slider.value)+1)%frames.length;show();},250);});show();
</script></html>'''.replace('DATA', json.dumps(rows)).replace('TITLE', escape(args.title)).replace('AFTER_LABEL', escape(args.after_label))
    (args.output/'index.html').write_text(page, encoding='utf-8')
    print(json.dumps(dict(matched_frames=len(rows), output=str(args.output/'index.html'))))


if __name__ == '__main__':
    main()
