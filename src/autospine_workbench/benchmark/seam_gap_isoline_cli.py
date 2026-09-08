"""Independent subpixel chord evidence, retaining the coarse boundary baseline."""
import argparse
from collections import Counter
import html
import json
import math
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..targets.spine43.continuous_pose import world
from ..targets.spine43.seam_raster import mask, texture
from ..targets.spine43.seam_gap_boundary import outside_reachable
from ..targets.spine43.seam_gap_isoline import contours, probe
from .seam_gap_boundary_cli import compile_report as coarse_report
from .seam_gap_context_cli import load
from .seam_gap_transport_cli import compile_report as transport


def compile_report(before, after, before_dir, after_dir):
    coarse,_ = coarse_report(before,after,before_dir,after_dir)
    source,page = transport(before,after,before_dir,after_dir)
    doc=json.loads(load(after,after_dir,'skeleton.json')); attachments=doc['skins'][0]['attachments']
    poses=[world(doc,i/30) for i in range(61)]; rows=[]
    for relation,comparison in zip(source['relations'],after['common_frame_comparison']['relations'],strict=True):
        names=[relation['driver'],relation['follower']]
        if names != [comparison['driver'],comparison['follower']]: raise ValueError('isoline_relation_order')
        textures={n:texture(load(after,after_dir,'editor/images/'+n+'.png')) for n in names}
        cached={}; tracks=[]
        for track in relation['tracks']:
            samples=[]
            for component in track['components']:
                tick=component['frame'];rect=comparison['frames'][tick]['rect']
                if tick not in cached:
                    fields=[mask(attachments[n][n],poses[tick][n],textures[n],rect) for n in names]
                    masks=[f>=8 for f in fields]
                    cached[tick]=([contours(f,rect) for f in fields],outside_reachable(masks[0]|masks[1]),masks)
                boundaries,reachable,masks=cached[tick]
                for point in component['pixels_world']:
                    x=math.floor(point[0])-rect[0];y=math.floor(-point[1])-rect[1]
                    if not (0<=x<rect[2] and 0<=y<rect[3]) or masks[0][y,x] or masks[1][y,x]:
                        raise ValueError('isoline_gap_replay')
                    sample=probe(point,boundaries)
                    sample.update(frame=tick,component_id=component['id'],roi_connectivity='reaches_roi_edge' if (y,x) in reachable else 'enclosed_in_roi')
                    samples.append(sample)
            tracks.append(dict(id=track['id'],start_frame=track['start_frame'],end_frame=track['end_frame'],
                               samples=samples,counts=dict(Counter(s['evidence'] for s in samples))))
        if sum(len(t['samples']) for t in tracks)!=relation['pixel_samples']: raise ValueError('isoline_pixel_conservation')
        rows.append(dict(driver=names[0],follower=names[1],tracks=tracks))
    report=dict(schema='autospine.seam-gap-isoline/v1',profile='cpu-sample-bilinear-alpha8-subdivide4-v1',
                source_boundary_sha256=canonical_sha256(coarse),
                source_transport_sha256=canonical_sha256(source),authority='none',production_authorized=False,
                status='needs_review',runtime_raster_status='not_evaluated',relations=rows)
    summary='<details open><summary>亚像素 alpha 等值轮廓证据（不是裂缝判决）</summary><p>距离和法向来自 CPU 样本双线性插值的 4 倍细分弦段近似，不是 GPU 等值线；ROI 连通不等于角色外部。每条轨迹的逐像素证据可展开。</p>'
    for row in rows:
        summary+='<h3>'+html.escape(row['driver']+' → '+row['follower'])+'</h3>'
        for track in row['tracks']:
            summary+='<details><summary>'+html.escape(f"{track['id']} · 帧 {track['start_frame']}–{track['end_frame']} · {track['counts']}")+'</summary><pre>'+html.escape(json.dumps(track['samples'],ensure_ascii=False,indent=2))+'</pre></details>'
    page=page.replace('<script>',summary+'</details><script>',1)
    overlay=json.dumps(rows,ensure_ascii=False).replace('<','\\u003c')
    page+='''<script>const isolineRows=OVERLAY;
function drawIsolineEvidence(){document.querySelectorAll('.isoline-guide').forEach(n=>n.remove());
const row=isolineRows[select.value];if(!row)return;
for(const t of row.tracks.filter(t=>track.value==='all'||t.id===track.value))for(const s of t.samples.filter(s=>s.frame===+slider.value)){
for(const [key,color] of [['driver_nearest','#063b8a'],['follower_nearest','#075323']])for(const n of s[key]){
const line=element('line',{x1:s.world_point[0],y1:-s.world_point[1],x2:n.point[0],y2:-n.point[1],stroke:color,'stroke-width':'.12'});line.setAttribute('class','isoline-guide');
const normal=element('line',{x1:n.point[0],y1:-n.point[1],x2:n.point[0]+n.normal[0]*.7,y2:-n.point[1]-n.normal[1]*.7,stroke:color,'stroke-width':'.16'});normal.setAttribute('class','isoline-guide');
}}}
for(const id of ['relation','track','viewport'])document.getElementById(id).addEventListener('change',drawIsolineEvidence);
slider.addEventListener('input',drawIsolineEvidence);drawIsolineEvidence();</script>'''.replace('OVERLAY',overlay)
    return report,page


def read_isoline(saved,before,after,before_dir,after_dir):
    expected,_=compile_report(before,after,before_dir,after_dir)
    if canonical_sha256(saved)!=canonical_sha256(expected): raise ValueError('isoline_reader_mismatch')
    return saved


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('before','after','before-dir','after-dir','output-dir'): p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    try:
        report,page=compile_report(json.loads(args.before.read_text()),json.loads(args.after.read_text()),args.before_dir,args.after_dir)
        digest=canonical_sha256(report);args.output_dir.mkdir(parents=True,exist_ok=True);target=args.output_dir/(digest+'.json')
        if target.exists() and canonical_sha256(json.loads(target.read_text()))!=digest: raise ValueError('isoline_existing_corrupt')
        target.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n',encoding='utf-8');(args.output_dir/'index.html').write_text(page,encoding='utf-8')
        print(json.dumps(dict(artifact_sha256=digest,counts=[dict(driver=r['driver'],counts=dict(Counter(s['evidence'] for t in r['tracks'] for s in t['samples']))) for r in report['relations']])));return 0
    except (ValueError,TypeError,KeyError,IndexError,OSError):
        print(json.dumps(dict(status='blocked',reason_code='isoline_input_or_replay_failed',authority='none')));return 1


if __name__=='__main__': raise SystemExit(main())
