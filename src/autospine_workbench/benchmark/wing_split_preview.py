"""Apply explicit mask strokes to a reversible diagnostic texture candidate."""
from copy import deepcopy
from hashlib import sha256
import base64
from PIL import Image
from .wing_split_draft import validate,rasterize
from .wing_spine_preview import encode
from ..asset.planning.wing_edge_ownership import decode,encode as png
from ..resolved_project import canonical_sha256


def build(source,files,draft):
    draft=validate(source,draft)
    if set(files)!=set(source['files']) or any(sha256(files[n]).hexdigest()!=digest for n,digest in source['files'].items()):
        raise ValueError('wing_split_source_files')
    raw=files['editor/images/topwear.png'];original=decode(raw);w,h=original.size
    if [w,h]!=draft['canvas']:raise ValueError('wing_split_image_canvas')
    mask=rasterize(source,draft);remaining=original.copy();removed=Image.new('RGBA',(w,h))
    region=next(r for r in source['regions'] if r['id']=='topwear');ox,oy=region['setup_vertices_xy'][0]
    hints=[r['canvas_bbox'] for r in source['review_queue']]
    counts=dict(removed_visible_pixels=0,kept_visible_pixels=0,removed_outside_hint_pixels=0,removed_inside_hint_pixels=0)
    for i,value in enumerate(mask):
        x,y=i%w,i//w;rgba=original.getpixel((x,y))
        if value==2 and rgba[3]:counts['kept_visible_pixels']+=1
        if value!=1:continue
        removed.putpixel((x,y),rgba);remaining.putpixel((x,y),(0,0,0,0))
        if not rgba[3]:continue
        counts['removed_visible_pixels']+=1
        inside=any(a<=x+ox<c and b<=y+oy<d for a,b,c,d in hints)
        counts['removed_inside_hint_pixels' if inside else 'removed_outside_hint_pixels']+=1
    rebuilt=Image.alpha_composite(remaining,removed);a,b=original.tobytes(),rebuilt.tobytes()
    if any(a[i+3]!=b[i+3] or (a[i+3] and a[i:i+4]!=b[i:i+4]) for i in range(0,len(a),4)):
        raise ValueError('wing_split_reconstruction')
    outputs=dict(files);outputs['editor/images/topwear.png']=png(remaining)
    page=Image.new('RGBA',(w+4,h+4));page.paste(remaining,(2,2));outputs['textures/topwear.png']=png(page)
    outputs['split/original-topwear.png']=raw;outputs['split/removed-topwear.png']=png(removed)
    outputs['split/mask.png']=png(Image.frombytes('L',(w,h),mask));outputs['split/draft.json']=encode(draft)
    report=deepcopy(source);report.update(schema='autospine.wing-split-preview/v1',profile='explicit-tristate-source-split-v1',
      source_edge_preview_sha256=canonical_sha256(source),source_split_draft_sha256=canonical_sha256(draft),
      split_counts=counts,source_reconstruction_exact=True,target_texture_unchanged=False,
      review_queue_scope='pre_split_overlap_hints_not_post_split_qa',
      split_reason_codes=['mask_extends_beyond_overlap_hints'] if counts['removed_outside_hint_pixels'] else [],
      split_review_status='needs_review',ghosting_resolved=False)
    outputs['README.txt']+=b'\nExplicit user mask candidate. Removed pixels preserved in split/removed-topwear.png; original in split/original-topwear.png. Mask outside overlap hints requires visual review.\n'
    def image(raw):return 'data:image/png;base64,'+base64.b64encode(raw).decode()
    outputs['review.html']=f'''<!doctype html><meta charset="utf-8"><title>实际拆分位置复核</title>
<style>body{{font:18px/1.7 system-ui;margin:30px;background:#f4f6f8;color:#243448}}main{{display:flex;gap:16px}}figure{{width:32%;margin:0}}img{{width:100%;background:repeating-conic-gradient(#ddd 0% 25%,white 0% 50%) 0/16px 16px}}</style>
<h1>按上传草稿生成的拆分候选</h1><p>{len(draft['strokes'])} 笔；移除 {counts['removed_visible_pixels']} 个可见像素，其中 {counts['removed_outside_hint_pixels']} 个位于原重叠提示框之外。提示框不是语义真值，请核对是否误涂服装。</p>
<p><a href="preview.zip">下载候选包</a> · <a href="split/draft.json">本次草稿</a> · <a href="preview-manifest.json">来源报告</a></p>
<main><figure><img src="{image(raw)}"><figcaption>原始上衣</figcaption></figure><figure><img src="{image(outputs['split/removed-topwear.png'])}"><figcaption>实际移除内容（完整保留）</figcaption></figure><figure><img src="{image(outputs['editor/images/topwear.png'])}"><figcaption>剩余上衣</figcaption></figure></main>
<p>仅改本候选上衣纹理；骨架、动作与其他附件不变。没有生产授权，未宣称翼片重影已修复。原图可由剩余图与移除图精确重建。</p>'''.encode()
    report['files']={n:sha256(raw).hexdigest() for n,raw in outputs.items()}
    outputs['preview-manifest.json']=encode(report)
    return report,outputs


def verify(saved,source,files,draft):
    expected,_=build(source,files,draft)
    if canonical_sha256(saved)!=canonical_sha256(expected):raise ValueError('wing_split_preview_replay')
    return deepcopy(saved)
