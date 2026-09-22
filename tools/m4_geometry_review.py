"""Export an exact candidate's geometry inspector using the workbench component."""
import argparse
import json
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
    html='''<!doctype html><meta charset="utf-8"><title>变形区域定位</title>
<style>body{background:#14202b;color:#eee;font:16px sans-serif;margin:24px}button,select,a{padding:8px;margin:8px;color:inherit;background:#243b50}section{margin:16px 0}</style>
<h1>红美铃 Squat · 当前候选异常定位</h1><p>此页验证工作台相同组件。时间按钮记录定位请求；真实动作请打开对应候选播放器。</p>
<output id="seek">尚未定位</output><main></main>
<script type="module">
import {appendGeometryDetails} from './motion-geometry-details.js';
const realFetch=window.fetch.bind(window);
window.fetch=(url,options)=>realFetch(url.endsWith('/geometry-details.json')?'./geometry-details.json':url,options);
appendGeometryDetails(document.querySelector('main'),{job_id:'diagnostic',result:{artifact_sha256:'DIGEST'}},
  time=>{document.querySelector('#seek').textContent=`定位请求：${time} 秒`;window.lastSeek=time;});
</script>'''.replace('DIGEST',digest)
    (output/'index.html').write_text(html,encoding='utf-8')
    print(json.dumps(dict(candidate=digest,rows=[dict(slot=r['slot'],failed=r['failed_area_triangles'],
          shown=r['shown'],first=r['details'][0] if r['details'] else None) for r in report['rows']]),ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();run(args.source,args.output)
