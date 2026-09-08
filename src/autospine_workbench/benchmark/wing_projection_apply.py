"""Consume explicit group/local choices on a compatible wing-back-order package."""
from copy import deepcopy
from hashlib import sha256
import base64
from PIL import Image
from .wing_projection_groups import effective_mask,validate
from .wing_spine_preview import encode
from ..asset.planning.wing_edge_ownership import decode,encode as png
from ..resolved_project import canonical_sha256


def build(source,files,candidate,edge,draft):
    draft=validate(candidate,edge,draft)
    if source['schema']!='autospine.wing-back-order-preview/v1' or source['authority']!='none' or source['production_authorized'] is not False:raise ValueError('projection_apply_source')
    if source['source_split_preview_sha256']!=candidate['source_preview_sha256']:raise ValueError('projection_apply_lineage')
    if set(files)!=set(source['files']) or any(sha256(files[n]).hexdigest()!=d for n,d in source['files'].items()):raise ValueError('projection_apply_files')
    raw=files['editor/images/topwear.png']
    if sha256(raw).hexdigest()!=candidate['target_image_sha256']:raise ValueError('projection_apply_target')
    original=decode(raw);w,h=original.size
    if [w,h]!=candidate['canvas']:raise ValueError('projection_apply_canvas')
    mask=effective_mask(candidate,edge,draft);remaining=original.copy();removed=Image.new('RGBA',(w,h));count=0
    for i,value in enumerate(mask):
        if not value:continue
        xy=(i%w,i//w);rgba=original.getpixel(xy);removed.putpixel(xy,rgba);remaining.putpixel(xy,(0,0,0,0));count+=rgba[3]>0
    rebuilt=Image.alpha_composite(remaining,removed);before,after=original.tobytes(),rebuilt.tobytes()
    if any(before[i+3]!=after[i+3] or (before[i+3] and before[i:i+4]!=after[i:i+4]) for i in range(0,len(before),4)):raise ValueError('projection_apply_reconstruction')
    outputs=dict(files);outputs['editor/images/topwear.png']=png(remaining)
    page=Image.new('RGBA',(w+4,h+4));page.paste(remaining,(2,2));outputs['textures/topwear.png']=png(page)
    outputs['projection/original-topwear.png']=raw;outputs['projection/removed-topwear.png']=png(removed)
    outputs['projection/mask.png']=png(Image.frombytes('L',(w,h),bytes(v*255 for v in mask)))
    outputs['projection/draft.json']=encode(draft)
    summary=dict(removed_visible_pixels=count,local_strokes=len(draft['local_strokes']),choices=draft['choices'],
      reconstruction_exact=True,prior_split_preserved=True,back_order_preserved=True)
    report=deepcopy(source);report.update(schema='autospine.wing-projection-applied/v1',profile='explicit-projection-mask-on-back-order-v1',
      source_back_order_sha256=canonical_sha256(source),source_projection_candidate_sha256=canonical_sha256(candidate),
      source_projection_draft_sha256=canonical_sha256(draft),projection_apply=summary,textures_unchanged=False,
      overlap_hints_scope='historical_before_cleanup',ghosting_resolved=False)
    outputs['README.txt']+=b'\nExplicit projection/local mask applied to topwear; wing-back order preserved. Rollback pixels in projection/. Visual acceptance still required.\n'
    def image(data):return 'data:image/png;base64,'+base64.b64encode(data).decode()
    outputs['review.html']=f'''<!doctype html><meta charset="utf-8"><title>主翼清理实际结果</title><style>body{{font:18px/1.7 system-ui;margin:30px;color:#243448;background:#f4f6f8}}main{{display:flex;gap:16px}}figure{{width:32%;margin:0}}img{{width:100%;background:repeating-conic-gradient(#ddd 0% 25%,white 0% 50%) 0/16px 16px}}</style>
<h1>按上传标注清理上衣</h1><p>本轮移除 {count} 个可见像素；{summary['local_strokes']} 笔局部修正。分组选择保持上传原值，没有自动把不确定改为移除。此前清理和主翼后置层序均保留。</p>
<p><a href="preview.zip">下载 Spine 候选</a> · <a href="projection/draft.json">上传草稿</a> · <a href="preview-manifest.json">报告</a></p>
<main><figure><img src="{image(raw)}"><figcaption>本轮之前</figcaption></figure><figure><img src="{image(outputs['projection/removed-topwear.png'])}"><figcaption>本轮移除内容（保留以便回退）</figcaption></figure><figure><img src="{image(outputs['editor/images/topwear.png'])}"><figcaption>清理后的上衣</figcaption></figure></main><p>骨骼、动作、UV、其他附件纹理不变。静态对照不代表完整角色视觉通过，无生产授权。</p>'''.encode()
    report['files']={n:sha256(raw).hexdigest() for n,raw in outputs.items()};outputs['preview-manifest.json']=encode(report)
    return report,outputs


def verify(saved,*inputs):
    if canonical_sha256(saved)!=canonical_sha256(build(*inputs)[0]):raise ValueError('projection_apply_replay')
    return deepcopy(saved)
