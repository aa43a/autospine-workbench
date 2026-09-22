"""Export an exact candidate's geometry inspector using the workbench component."""
import argparse
import json
import shutil
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.motion_geometry_details import build


def run(source, output):
    receipt=json.loads((source/'report.json').read_text(encoding='utf-8'))
    digest=receipt['candidate_bundle_sha256']
    report=build(AnimatedStore(source/'isolated-store').read(digest),digest)
    output.mkdir(parents=True,exist_ok=True)
    (output/'geometry-details.json').write_text(json.dumps(report,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    module=Path('web/modules/motion-geometry-details.js').read_text(encoding='utf-8')
    (output/'motion-geometry-details.js').write_text(module,encoding='utf-8')
    assets=output/'player-assets';assets.mkdir(exist_ok=True)
    for name in ('scene.json','runtime.js'):
        shutil.copyfile(source/'runtime/player-assets'/name,assets/name)
    scene=json.loads((assets/'scene.json').read_text(encoding='utf-8'))
    if scene['artifact_sha256']!=digest:raise ValueError('geometry_review_player_identity')
    for name,target in (('character-player.js','client.js'),('character-player-inspection.js','inspection.js'),
                        ('character-player.css','style.css')):
        shutil.copyfile(Path('web')/name,assets/target)
    shutil.copyfile('web/character-player.html',output/'player.html')
    html='''<!doctype html><meta charset="utf-8"><title>变形区域定位</title>
<style>body{background:#14202b;color:#eee;font:16px sans-serif;margin:24px}button,select,a{padding:8px;margin:8px;color:inherit;background:#243b50}section{margin:16px 0}</style>
<h1>红美铃 Squat · 同帧原纹理与动作区域</h1><p>同一候选的只读诊断，不代表动作验收通过。</p>
<iframe title="当前候选动作" src="player.html" style="width:100%;height:700px"></iframe>
<output id="seek">尚未定位</output><main></main>
<script type="module">
import {appendGeometryDetails} from './motion-geometry-details.js';
const realFetch=window.fetch.bind(window);
window.fetch=(url,options)=>realFetch(url.endsWith('/geometry-details.json')?'./geometry-details.json':url,options);
appendGeometryDetails(document.querySelector('main'),{job_id:'diagnostic',result:{artifact_sha256:'DIGEST'}},
  time=>{const control=document.querySelector('iframe').contentWindow.characterPlayerControl;
    if(control?.artifact!=='DIGEST'||!control.seek(time))throw Error('播放器未就绪或候选不匹配');
    document.querySelector('#seek').textContent=`已定位：${time} 秒`;window.lastSeek=time;},
  (slot,triangle,animation)=>document.querySelector('iframe').contentWindow.characterPlayerControl.inspectTriangle(slot,triangle,animation));
</script>'''.replace('DIGEST',digest)
    (output/'index.html').write_text(html,encoding='utf-8')
    print(json.dumps(dict(candidate=digest,rows=[dict(slot=r['slot'],failed=r['failed_area_triangles'],
          shown=r['shown'],first=r['details'][0] if r['details'] else None) for r in report['rows']]),ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();run(args.source,args.output)
