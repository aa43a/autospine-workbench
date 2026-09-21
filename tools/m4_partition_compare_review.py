"""Timeline review for captured partition/order experiments; never accepts them."""
import argparse
import json
from pathlib import Path


def render(folder):
    report=json.loads((folder/'runtime-comparison.json').read_bytes())
    captures={name:json.loads((folder/name/'runtime/report.json').read_bytes()) for name in ('before','after')}
    frames=[]
    for index,row in enumerate(report['frames']):
        paths={}
        for name,capture in captures.items():
            if capture['bundle_sha256']!=report['bundles'][name] or capture['results'][index]['time']!=row['time']:
                raise ValueError('partition_review_identity')
            frame=next(r for r in capture['screenshots'] if r['index']==index)
            paths[name]=name+'/runtime/'+frame['file']
        frames.append(dict(row,**paths))
    payload=json.dumps(frames).replace('<','\\u003c')
    peak=max(range(len(frames)),key=lambda i:frames[i]['changed_pixels'])
    page='''<!doctype html><meta charset="utf-8"><title>M4 局部遮挡对比</title>
<style>body{font:16px sans-serif;background:#182531;color:#eee;margin:24px}button,input{padding:10px}#time{width:65%}main{display:flex;gap:20px}figure{width:48%;margin:0}img{width:100%;max-height:75vh;object-fit:contain;background:repeating-conic-gradient(#34424e 0% 25%,#263540 0% 50%) 0/20px 20px}a{color:#8dd8ff}</style>
<h1>局部遮挡 · 同帧对比</h1><p>实验候选，未自动采用。数值通过不代表视觉正确；请特别检查胸前袖布片段和相邻区域的显示连续性。</p>
<p>播放的是已捕获的官方 Runtime 帧，时间轴不补造帧间画面。</p>
<button id="play">播放</button> <button id="peak">最大差异帧</button> <input id="time" aria-label="时间轴" type="range" min="0" step="1"><output id="label"></output>
<p id="stats"></p><main><figure><figcaption>原候选</figcaption><img id="before" alt="原候选同帧画面"></figure><figure><figcaption>实验候选</figcaption><img id="after" alt="实验候选同帧画面"></figure></main>
<p><a href="runtime-comparison.json">捕获与像素差异证据</a> · <a href="report.json">候选与保留异常</a></p><script>
const frames=PAYLOAD,peak=PEAK;
const slider=document.querySelector('#time'),button=document.querySelector('#play');
let playing=false,start=0;slider.max=frames.length-1;
function show(i){slider.value=i;const f=frames[i];document.querySelector('#label').textContent=f.time.toFixed(6)+' s';
for(const name of ['before','after'])document.querySelector('#'+name).src=f[name];
document.querySelector('#stats').textContent='第 '+(i+1)+' / '+frames.length+' 帧；改变像素 '+f.changed_pixels+'；最大通道差 '+f.max_channel_delta;}
function stop(){playing=false;button.textContent='播放';}
function step(now){if(!playing)return;let t=(now-start)/1000;if(t>frames.at(-1).time){stop();show(frames.length-1);return;}
let i=0;while(i+1<frames.length&&frames[i+1].time<=t)i++;show(i);requestAnimationFrame(step);}
button.onclick=()=>{if(playing){stop();return;}if(+slider.value===frames.length-1)show(0);playing=true;button.textContent='暂停';start=performance.now()-frames[+slider.value].time*1000;requestAnimationFrame(step);};
slider.oninput=()=>{stop();show(+slider.value);};document.querySelector('#peak').onclick=()=>{stop();show(peak);};show(0);
</script>'''.replace('PAYLOAD',payload).replace('PEAK',str(peak))
    (folder/'index.html').write_text(page,encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder',type=Path)
    render(parser.parse_args().folder)
