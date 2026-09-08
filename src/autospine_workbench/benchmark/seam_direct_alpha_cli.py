"""Subpixel direct UV alpha probes on immutable isoline sample coordinates."""
import argparse
import base64
from io import BytesIO
import html
import json
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..targets.spine43.continuous_pose import world
from ..targets.spine43.seam_raster import mask,texture
from ..targets.spine43.seam_direct_alpha import sample,patch
from .seam_gap_context_cli import load
from .seam_gap_isoline_cli import compile_report as isoline


def compile_report(before,after,before_dir,after_dir):
    import numpy as np
    from PIL import Image
    source,_=isoline(before,after,before_dir,after_dir)
    docs=[json.loads(load(r,d,'skeleton.json')) for r,d in ((before,before_dir),(after,after_dir))]
    poses=[[world(d,i/30) for i in range(61)] for d in docs];rows=[];cards=[]
    for relation in source['relations']:
        names=[relation['driver'],relation['follower']]
        attachments=[docs[1]['skins'][0]['attachments'][n][n] for n in names]
        textures=[texture(load(after,after_dir,'editor/images/'+n+'.png')) for n in names];records=[]
        for track in relation['tracks']:
            for entry in track['samples']:
                point=entry['world_point'];tick=entry['frame'];p=[poses[1][tick][n] for n in names]
                center=[sample(a,v,t,[point]) for a,v,t in zip(attachments,p,textures)]
                values=[float(x[0][0]) for x in center]
                native=[float(mask(a,v,t,[int(point[0]-.5),int(-point[1]-.5),1,1])[0,0]) for a,v,t in zip(attachments,p,textures)]
                if max(abs(a-b) for a,b in zip(values,native))>1e-8 or any(v>=8 for v in values):
                    raise ValueError('direct_alpha_native_replay')
                base=[sample(docs[0]['skins'][0]['attachments'][n][n],poses[0][tick][n],t,[point])[0][0] for n,t in zip(names,textures)]
                if max(base)<8: raise ValueError('direct_alpha_not_new_gap')
                coarse,_=patch(point,attachments,p,textures,8);fine,alpha=patch(point,attachments,p,textures,16)
                record=dict(track_id=track['id'],frame=tick,world_point=point,center_alpha=values,
                            center_mesh_covered=[bool(x[1][0]) for x in center],baseline_center_alpha=[float(v) for v in base],
                            patch8=coarse,patch16=fine,union_gap_fraction_change=abs(coarse['union_below8']/64-fine['union_below8']/256))
                records.append(record)
                if len(records)<=3:
                    buf=BytesIO();Image.fromarray(np.clip(alpha,0,255).astype('uint8')).save(buf,format='PNG')
                    cards.append('<figure><figcaption>'+html.escape(f'{names[0]} · 帧 {tick} · {point}')+'</figcaption><img width="160" height="160" src="data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()+'"></figure>')
        rows.append(dict(driver=names[0],follower=names[1],samples=records))
    report=dict(schema='autospine.seam-direct-alpha/v1',profile='direct-uv-bilinear-cell8-16-v1',
                source_isoline_sha256=canonical_sha256(source),authority='none',production_authorized=False,status='needs_review',
                runtime_raster_status='not_evaluated',relations=rows)
    page='<!doctype html><meta charset="utf-8"><title>直接 UV alpha 核查</title><style>body{font:17px system-ui;margin:30px}img{image-rendering:pixelated;border:1px solid #aaa}figure{display:inline-block}pre{white-space:pre-wrap}</style><h1>直接 UV alpha 核查</h1><p>每张图只覆盖一个原始像素单元，放大显示 16×16 直接采样。黑＝透明，白＝不透明。这是 alpha 图，不是角色最终颜色或 Runtime 截图。每关系展示按原顺序前三个样本。</p>'+''.join(cards)
    for row in rows:
        page+='<details><summary>'+html.escape(row['driver']+f" · {len(row['samples'])} 个样本")+'</summary><pre>'+html.escape(json.dumps(row['samples'],indent=2))+'</pre></details>'
    if not rows: page+='<p>没有接缝候选，不计为通过。</p>'
    return report,page


def read_direct(saved,before,after,before_dir,after_dir):
    expected,_=compile_report(before,after,before_dir,after_dir)
    if canonical_sha256(saved)!=canonical_sha256(expected): raise ValueError('direct_alpha_reader_mismatch')
    return saved


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('before','after','before-dir','after-dir','output-dir'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    try:
        report,page=compile_report(json.loads(args.before.read_text()),json.loads(args.after.read_text()),args.before_dir,args.after_dir)
        digest=canonical_sha256(report);args.output_dir.mkdir(parents=True,exist_ok=True);target=args.output_dir/(digest+'.json')
        if target.exists() and canonical_sha256(json.loads(target.read_text()))!=digest: raise ValueError('direct_alpha_existing_corrupt')
        target.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n',encoding='utf-8');(args.output_dir/'index.html').write_text(page,encoding='utf-8')
        print(json.dumps(dict(artifact_sha256=digest,relations=[dict(driver=r['driver'],samples=len(r['samples']),min_gap_fraction=min((s['patch16']['union_below8']/256 for s in r['samples']),default=None),max_fraction_change=max((s['union_gap_fraction_change'] for s in r['samples']),default=None)) for r in report['relations']])));return 0
    except (ValueError,TypeError,KeyError,IndexError,OSError):
        print(json.dumps(dict(status='blocked',reason_code='direct_alpha_input_or_replay_failed',authority='none')));return 1


if __name__=='__main__':raise SystemExit(main())
