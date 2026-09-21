"""Draggable exact-capture timeline for a source-bound torso experiment."""
import argparse
from hashlib import sha256
import json
from pathlib import Path


def render(root):
    report=json.loads((root/'report.json').read_bytes())
    capture=json.loads((root/'runtime/report.json').read_bytes())
    if not capture['passed'] or capture['bundle_sha256']!=report['candidate_bundle_sha256']:
        raise ValueError('torso_review_capture_identity')
    rows={(r['animation'],r['index']):r for r in capture['results']}
    frames=[]
    for shot in capture['screenshots']:
        file=root/'runtime'/shot['file']
        if not file.resolve().is_relative_to((root/'runtime').resolve()):raise ValueError('capture_path')
        if sha256(file.read_bytes()).hexdigest()!=shot['sha256']:raise ValueError('capture_image_identity')
        frames.append(dict(time=rows[shot['animation'],shot['index']]['time'],file='runtime/'+shot['file']))
    data=json.dumps(frames).replace('<','\\u003c')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>躯干投影候选</title>
<style>body{background:#17222e;color:#edf5ff;font:16px system-ui;margin:24px}header{position:sticky;top:0;background:#17222ef5;padding:12px}input{width:min(60vw,700px)}button{padding:8px 18px}img{height:72vh;max-width:95vw;object-fit:contain;background:repeating-conic-gradient(#34424e 0% 25%,#263540 0% 50%) 0/24px 24px}a{color:#8dddff}</style>
<header><h1>躯干投影候选 · 官方捕获时间轴</h1><p>依据双肩与骨盆的投影改变躯干形状，补偿头部和手臂。
这是烘焙到网格的实验候选，骨骼编辑辅助线保持原位置；没有生成侧背面素材。</p>
<p>几何与 Runtime 已检查；接触、遮挡与视觉尚未重新验收。当前候选未采用。</p>
<button id="play">播放</button> <input id="time" type="range" min="0" step="1" aria-label="动画时间轴"><output id="clock"></output>
<p><a href="report.json">来源与变形记录</a> · <a href="runtime/report.json">Runtime 证据</a></p></header>
<img id="frame" alt="官方 Runtime 捕获帧"><script>
const frames=DATA,slider=document.querySelector('#time'),clock=document.querySelector('#clock'),button=document.querySelector('#play');
slider.max=frames.length-1;slider.value=0;let playing=false,start=0,origin=0;
function show(){const i=+slider.value;document.querySelector('#frame').src=frames[i].file;clock.textContent=frames[i].time.toFixed(3)+' 秒 · '+(i+1)+'/'+frames.length;}
slider.oninput=()=>{playing=false;button.textContent='播放';show();};
button.onclick=()=>{playing=!playing;button.textContent=playing?'暂停':'播放';start=performance.now();origin=frames[+slider.value].time;if(playing)requestAnimationFrame(tick);};
function tick(now){if(!playing)return;const time=(origin+(now-start)/1000)%frames.at(-1).time;let i=0;while(i+1<frames.length&&frames[i+1].time<=time)i++;if(+slider.value!==i){slider.value=i;show();}requestAnimationFrame(tick);}show();
</script></html>'''.replace('DATA',data)
    (root/'review.html').write_text(page,encoding='utf-8')
    print(json.dumps(dict(frames=len(frames),page=str(root/'review.html'))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path)
    render(parser.parse_args().root)
