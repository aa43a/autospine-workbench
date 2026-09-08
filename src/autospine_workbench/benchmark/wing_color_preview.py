"""Reversible color ownership candidate over unchanged wing bones and draw order."""
from copy import deepcopy
from hashlib import sha256
import base64
from PIL import Image
from .wing_spine_preview import encode
from ..asset.planning.wing_edge_ownership import decode,encode as png
from ..asset.planning.wing_color_ownership import transfer
from ..resolved_project import canonical_sha256


def build(source,files):
    if source['schema']!='autospine.wing-projection-applied/v1' or source['authority']!='none' or source['production_authorized'] is not False:raise ValueError('wing_color_source')
    if set(files)!=set(source['files']) or any(sha256(files[n]).hexdigest()!=d for n,d in source['files'].items()):raise ValueError('wing_color_files')
    regions={r['id']:r for r in source['regions']};names=sorted(n for n in regions if n.startswith('wing-c'))
    if not names:raise ValueError('wing_color_components_missing')
    parts={n:files['editor/images/'+n+'.png'] for n in names};origins={n:regions[n]['setup_vertices_xy'][0] for n in names}
    donor=files['projection/removed-topwear.png'];origin=regions['topwear']['setup_vertices_xy'][0]
    combined,transfers,residual,qa=transfer(donor,origin,parts,origins)
    outputs=dict(files)
    for name,raw in combined.items():
        image=decode(raw);w,h=image.size;page=Image.new('RGBA',(w+4,h+4));page.paste(image,(2,2))
        outputs['editor/images/'+name+'.png']=raw;outputs['textures/'+name+'.png']=png(page)
        outputs['color/original-'+name+'.png']=parts[name];outputs['color/transferred-'+name+'.png']=transfers[name]
    outputs['color/unassigned.png']=residual;outputs['color/ownership.json']=encode(qa)
    report=deepcopy(source);report.update(schema='autospine.wing-color-preview/v1',profile=qa['profile'],
      source_cleaned_preview_sha256=canonical_sha256(source),donor_sha256=sha256(donor).hexdigest(),color_ownership=qa,
      topwear_unchanged=True,bone_motion_order_unchanged=True,color_transfer_status='needs_review')
    outputs['README.txt']+=b'\nSaved donor colors transferred into unique closed wing envelopes without warp or dilation. Outside pixels remain in color/unassigned.png. Original outlines, source donor, bones, tracks and slot order preserved. Review required.\n'
    def image(raw):return 'data:image/png;base64,'+base64.b64encode(raw).decode()
    rows=''.join(f'<section><h2>{n}: 转入 {qa["components"][n]["transferred_pixels"]} 像素</h2><div><figure><img src="{image(parts[n])}"><figcaption>原轮廓</figcaption></figure><figure><img src="{image(transfers[n])}"><figcaption>从保存图转入的像素</figcaption></figure><figure><img src="{image(combined[n])}"><figcaption>组合翼片候选</figcaption></figure></div></section>' for n in names)
    outputs['review.html']=f'''<!doctype html><meta charset="utf-8"><title>翼片颜色归属候选</title><style>body{{font:18px/1.7 system-ui;margin:30px;color:#243448;background:#f4f6f8}}div{{display:flex;gap:12px}}figure{{width:32%;margin:0}}img{{width:100%;background:repeating-conic-gradient(#ddd 0% 25%,white 0% 50%) 0/16px 16px}}</style>
<h1>已保存彩色像素 → 独立运动翼片</h1><p>唯一封闭区域转移 {qa['counts']['transferred']} 像素，歧义 {qa['counts']['ambiguous']}，封闭区域外 {qa['counts']['outside_closed_envelopes']}。无扩张、无变形配准、无生成补全，未归属像素另存。</p>
<p><a href="preview.zip">下载 Spine 候选</a> · <a href="color/ownership.json">归属报告</a> · <a href="color/unassigned.png">未归属像素</a></p>{rows}
<p>使用原根部、动作和后置层序，清理后的上衣不变。颜色覆盖与轮廓配准仍需视觉复核，没有生产授权。</p>'''.encode()
    report['files']={n:sha256(raw).hexdigest() for n,raw in outputs.items()};outputs['preview-manifest.json']=encode(report)
    return report,outputs


def verify(saved,source,files):
    if canonical_sha256(saved)!=canonical_sha256(build(source,files)[0]):raise ValueError('wing_color_replay')
    return deepcopy(saved)
