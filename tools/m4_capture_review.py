"""Pair immutable captured frames with the existing live timeline player."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path


def run(folder):
    receipt=json.loads((folder/'report.json').read_bytes())
    runtime=folder/'runtime';capture=json.loads((runtime/'report.json').read_bytes())
    if not capture['passed'] or capture['bundle_sha256']!=receipt['candidate_bundle_sha256']:
        raise ValueError('capture_review_identity')
    if not (runtime/'player.html').is_file():raise ValueError('capture_review_player_missing')
    cards=[]
    for row in capture['screenshots']:
        path=runtime/row['file']
        if runtime.resolve() not in path.resolve().parents:raise ValueError('capture_review_path')
        if sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('capture_review_image_changed')
        time=receipt['times'][row['index']]
        cards.append(f'<a target="live" href="player.html?time={time}"><img loading="lazy" src="{escape(row["file"],quote=True)}" alt="捕获 {time:.6f} 秒"><span>{time:.6f} 秒 · 定位播放</span></a>')
    page='''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>M4 实际渲染与时间轴对照</title><style>
body{margin:0;background:#15212b;color:#edf3f8;font:15px system-ui}header{padding:16px 24px;border-bottom:1px solid #52616d}
h1{font-size:21px;margin:0 0 8px}p{margin:6px 0;line-height:1.6}.layout{display:grid;grid-template-columns:minmax(460px,1fr) 360px;gap:12px;padding:12px}
iframe{width:100%;height:82vh;border:1px solid #52616d;background:#101920}.shots{height:82vh;overflow:auto;display:grid;grid-template-columns:1fr 1fr;gap:10px}
a{color:#a3ddff;text-decoration:none}a img{width:100%;height:210px;object-fit:contain;background:repeating-conic-gradient(#34424e 0% 25%,#263540 0% 50%) 0/20px 20px}
a span{display:block;padding:5px}.warn{color:#ffd691}@media(max-width:900px){.layout{grid-template-columns:1fr}.shots{height:300px;grid-template-columns:repeat(4,1fr)}}
</style><header><h1>M4 实际渲染与时间轴对照</h1>
<p class="warn">实验候选，尚未采用。Runtime 技术捕获通过不代表外观、遮挡或接触已验收。</p>
<p>左侧可播放、暂停和拖动时间轴；点击右侧真实捕获帧，可定位到相同时间。截图仅覆盖诊断时刻。</p>
<p>候选：DIGEST · <a href="report.json">捕获证据</a> · <a href="player.html" target="_blank">单独打开播放器</a></p></header>
<main class="layout"><iframe name="live" title="官方 Runtime 实时播放器" src="player.html?time=0"></iframe><section class="shots">CARDS</section></main>'''
    with (runtime/'review.html').open('x',encoding='utf-8') as f:
        f.write(page.replace('DIGEST',escape(receipt['candidate_bundle_sha256'])).replace('CARDS',''.join(cards)))
    print(json.dumps(dict(frames=len(cards),page=str(runtime/'review.html'))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path)
    run(p.parse_args().folder)
