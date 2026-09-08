"""Inspect existing verified native framebuffer crops; no new rendering or adoption."""
import argparse
import hashlib
import html
from io import BytesIO
import json
import math
from pathlib import Path

from PIL import Image
from ..resolved_project import canonical_sha256
from ..targets.spine43.seam_roi_context import analyze
from .seam_boundary_comparison import read_comparison


def compile_report(config_path, character):
    config = json.loads(config_path.read_bytes())
    entries = [e for e in config['characters'] if e['character'] == character]
    if len(entries) != 1:
        raise ValueError('roi_character')
    entry = entries[0]['boundary_comparison']
    resolve = lambda key: (config_path.parent / entry[key]).resolve()
    comparison = json.loads(resolve('report').read_bytes())
    read_comparison(comparison, *(resolve(k) for k in ('reference','reference_manifest','probe','runtime','candidate','manifest')))
    runtime = json.loads(resolve('runtime').read_bytes())
    captures = {(c['sample_index'], c['variant']): c for c in runtime['captures']
                if c['mode']=='all' and c['atlas']=='shared' and c['scale']==1}
    rows, images = [], {}
    for i, sample in enumerate(comparison['samples']):
        pair = [captures[i, v] for v in ('before', 'after')]
        if pair[0]['world_rect'] != pair[1]['world_rect']:
            raise ValueError('roi_framing')
        alpha = []
        for c in pair:
            raw = (resolve('runtime').parent / c['file']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != c['png_sha256']:
                raise ValueError('roi_image_identity')
            with Image.open(BytesIO(raw)) as image:
                if image.size != (32,32): raise ValueError('roi_dimensions')
                values = list(image.convert('RGBA').getchannel('A').get_flattened_data())
            alpha.append([values[y*32:(y+1)*32] for y in range(32)])
            images[c['file']] = raw
        left, bottom, _, _ = pair[0]['world_rect']
        center = [math.floor(sample['world_point'][0])-left,31-(math.floor(sample['world_point'][1])-bottom)]
        result = analyze(*alpha, center)
        result['components_8connected'] = analyze(*alpha, center, connectivity=8)['components']
        if [result['center_before_alpha'],result['center_after_alpha']] != [sample['before_alpha'],sample['after_alpha']]:
            raise ValueError('roi_target_mismatch')
        rows.append(dict(sample_index=i,frame=sample['frame'],pair_index=sample['pair_index'],center=center,
                         alpha_loss=sample['alpha_loss'],before_image=pair[0]['file'],after_image=pair[1]['file'],**result))
    return dict(profile='runtime-alpha8-4-8connected-roi-context-v1',authority='none',production_authorized=False,
                status='needs_review',character=character,source_comparison_sha256=canonical_sha256(comparison),
                scope='overlapping_32px_native_all_candidate_regions_crops',rows=rows), images


def page(report):
    view = '<!doctype html><meta charset="utf-8"><style>body{font:17px system-ui;margin:30px}img,svg{width:256px;height:256px;image-rendering:pixelated;background:repeating-conic-gradient(#ccc 0% 25%,white 0% 50%) 0/16px 16px}figure{display:inline-block;margin:8px}</style><h1>同帧局部空间复核</h1><p>按中心alpha下降排序。左原动画、中候选、右新增低于alpha8的位置（红：局部封闭；蓝：连到裁剪边缘；黑框：目标单元）。ROI互相重叠，不累加为独立裂缝。连到裁剪边缘不能证明角色外部；局部封闭也不证明接缝损坏。</p>'
    for row in sorted(report['rows'],key=lambda r:(-r['alpha_loss'],r['sample_index'])):
        view += '<details'+(' open' if row['alpha_loss']==max(r['alpha_loss'] for r in report['rows']) else '')+'><summary>'+html.escape(f"帧{row['frame']} / 配对{row['pair_index']}：alpha {row['center_before_alpha']}→{row['center_after_alpha']}，新增低alpha {row['new_low_alpha_pixels']}px")+'</summary>'
        for key, label in (('before_image','原'),('after_image','候选')):
            view += f'<figure><figcaption>{label}</figcaption><img loading="lazy" src="{html.escape(row[key],quote=True)}"></figure>'
        view += '<figure><figcaption>新增低alpha空间分布</figcaption><svg viewBox="0 0 32 32">'
        for c in row['components']:
            color = '#d33' if c['context']=='enclosed_in_roi' else '#1678cf'
            for x,y in c['new_pixels']: view += f'<rect x="{x}" y="{y}" width="1" height="1" fill="{color}"/>'
        x,y=row['center'];view+=f'<rect x="{x}" y="{y}" width="1" height="1" fill="none" stroke="black" stroke-width=".15"/></svg></figure>'
        enclosed=sum(len(c['new_pixels']) for c in row['components_8connected'] if c['context']=='enclosed_in_roi')
        view+=f'<p>考虑对角连通后，仍位于局部封闭区域的新增低alpha像素：{enclosed}。右图按4邻接标色，非全角色拓扑。</p></details>'
    return view


def read_report(saved, config_path, character):
    expected, _ = compile_report(config_path, character)
    if canonical_sha256(saved) != canonical_sha256(expected):
        raise ValueError('roi_context_replay')
    return saved


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--character',required=True);p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args();report,images=compile_report(args.config,args.character)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    target=args.output_dir/(canonical_sha256(report)+'.json')
    if target.exists() and json.loads(target.read_bytes())!=report:raise ValueError('roi_existing_corrupt')
    target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    for name,raw in images.items():(args.output_dir/name).write_bytes(raw)
    (args.output_dir/'index.html').write_text(page(report),encoding='utf-8')
    rows=report['rows']
    print(json.dumps(dict(artifact=target.stem,roi_count=len(rows),rois_with_new_low_alpha=sum(r['new_low_alpha_pixels']>0 for r in rows),
                         rois_with_enclosed_new=sum(any(c['context']=='enclosed_in_roi' for c in r['components']) for r in rows),top=max(rows,key=lambda r:r['alpha_loss']))))


if __name__=='__main__':main()
