"""Capture exact unchanged candidates at representative unresolved depth times."""
import argparse
from collections import Counter
from hashlib import sha256
import html
import json
from pathlib import Path
import subprocess

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.sleeve_capture_environment import discover
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import write
from autospine_workbench.targets.character43.runtime_storage_reference import build as storage
from autospine_workbench.targets.character43.motion_depth_overlap import Probe


def selected(report):
    rows=[r for r in report['records'] if r['check']['status']=='requires_partition_or_more_depth']
    groups={}
    for row in rows:groups.setdefault(tuple(row['pair']),[]).append(row)
    result=[]
    for pair,items in groups.items():
        items.sort(key=lambda r:r['check']['time'])
        picks=[items[0],max(items,key=lambda r:r['check']['counts']['ambiguous']),items[-1]]
        result.extend(picks)
    return result


def framebuffer_rect(rect,info):
    x,y,w,h=rect
    left=x-info['left'];top=y+info['bottom']+info['height']
    if left<0 or top<0 or left+w>info['width'] or top+h>info['height']:
        raise ValueError('local_capture_roi_outside_framebuffer')
    return left,top,w,h


def run(report_path,output):
    raw=report_path.read_bytes();report=json.loads(raw)
    if report.get('authority')!='none' or report.get('selected') is not False:
        raise ValueError('diagnostic_report_required')
    rows=selected(report);times=sorted({r['check']['time'] for r in rows})
    if not times or len(times)>24:raise ValueError('local_capture_sample_limit')
    source=AnimatedStore(Path('workspace')).read(report['artifact_sha256'])
    document=json.loads(source['skeleton.json'])
    frames=[dict(time=t,vertices=sample(document,'external-motion',t)[0]) for t in times]
    files={n:v for n,v in source.items() if n.endswith('.png') or n in ('skeleton.json','skeleton.atlas')}
    files['character-manifest.json']=canonical_bytes(dict(authority='none',production_authorized=False,
        source_artifact_sha256=report['artifact_sha256'],scope='unchanged_candidate_selected_depth_frames'))
    files=write(files,dict(skeleton_sha256=sha256(source['skeleton.json']).hexdigest(),
                          animations={'external-motion':frames}))
    output.mkdir(parents=True,exist_ok=True)
    store=AnimatedStore(output/'isolated-store');digest=store.publish(files)
    storage_path=output/'storage.json';storage_path.write_bytes(canonical_bytes(storage(files)))
    env=discover(Path.cwd().parent)
    if not env:raise ValueError('official_capture_environment_missing')
    command=['node','tools/capture-character-runtime.mjs',str((store.root/digest).resolve()),
             str((output/'runtime').resolve()),env[1],env[3],'1','{}',str(storage_path.resolve())]
    with (output/'capture.log').open('wb') as log:
        process=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=300,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if process.returncode:raise ValueError('local_official_capture_failed')
    capture=json.loads((output/'runtime/report.json').read_bytes())
    if not capture['passed'] or capture['bundle_sha256']!=digest:
        raise ValueError('local_capture_identity')
    from PIL import Image
    probe=Probe(document,source,'external-motion',tiled=True,sparse=True,rendered_bounds=True)
    cards=[];entries=[];seen=set()
    for row in rows:
        pair=row['pair'];time=row['check']['time'];key=(*pair,time)
        if key in seen:continue
        seen.add(key);index=times.index(time)
        frame=next(s for s in capture['screenshots'] if s['index']==index)
        image_raw=(output/'runtime'/frame['file']).read_bytes()
        if sha256(image_raw).hexdigest()!=frame['sha256']:raise ValueError('local_capture_image_identity')
        actual=capture['results'][index]
        if actual['time']!=time:raise ValueError('local_capture_time_identity')
        rect=probe.pair(*pair,time)['roi']
        left,top,w,h=framebuffer_rect(rect,capture['info'])
        name='roi-'+str(len(entries))+'.png'
        with Image.open(output/'runtime'/frame['file']) as image:
            image.crop((left,top,left+w,top+h)).save(output/name)
        entry=dict(pair=pair,time=time,source_tick=row['source_tick'],counts=row['check']['counts'],
                   roi=rect,file=name,sha256=sha256((output/name).read_bytes()).hexdigest(),
                   framebuffer=frame,screen_rect=[left,top,w,h])
        entries.append(entry)
        label=html.escape(' / '.join(pair))
        cards.append(f'<figure><h2>{label} · {time:.6f}s</h2><img src="{name}"><p>{html.escape(str(entry["counts"]))}</p>'
                     f'<a href="runtime/{frame["file"]}">完整同帧画面</a></figure>')
    result=dict(profile='local-depth-official-framebuffer-review-v1',source_artifact_sha256=report['artifact_sha256'],
        skeleton_sha256=sha256(source['skeleton.json']).hexdigest(),diagnostic_sha256=sha256(raw).hexdigest(),
        capture_bundle_sha256=digest,frames=entries,input_status_counts=dict(Counter(r['check']['status'] for r in report['records'])),authority='none',selected=False,
        scope='representative_overlap_roi_visual_review_not_depth_truth_or_acceptance')
    (output/'report.json').write_bytes(canonical_bytes(result))
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>局部深度 Runtime 复核</title>'
        '<style>body{background:#182531;color:#eee;font:16px sans-serif}main{display:flex;flex-wrap:wrap}figure{max-width:48%;margin:12px}img{max-width:100%;background:repeating-conic-gradient(#34424e 0% 25%,#263540 0% 50%) 0/20px 20px}a{color:#8dd8ff}</style>'
        '<h1>局部深度 · 官方 Runtime 同帧画面</h1><p>保留当前绘制顺序。显示已测异常中的首帧、歧义像素最多帧和末帧，不覆盖未测记录；计数来自 CPU 深度模型，图像来自官方 Runtime。画面本身不能证明深度正确，不代表自动验收。</p>'
        f'<p>完整输入状态：{html.escape(str(result["input_status_counts"]))}</p>'
        '<a href="report.json">身份与定位记录</a><main>'+''.join(cards)+'</main>',encoding='utf-8')
    print(json.dumps(dict(frames=len(times),regions=len(entries),artifact=report['artifact_sha256'],
                         max_error_px=max(r['max_error_px'] for r in capture['results']))),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();run(args.report,args.output)
