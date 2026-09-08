"""Show anatomical left/right and unresolved residual at original offsets."""
import hashlib
from io import BytesIO
from html import escape
from .semantic_view import _image_url


def render_partitions(candidate,composite,views):
    w,h=candidate['canvas'];background=_image_url(composite,candidate['composite_sha256']);cards=[]
    for source,parts,qa in views:
        x,y,r,b=source['bbox'];panels=[]
        for name,label,code in (('left','角色左侧','1'),('right','角色右侧','2'),('residual','待定残余','3')):
            raw=parts[name+'.png'];url=_image_url(raw,hashlib.sha256(raw).hexdigest())
            diagnostic=''
            if name=='residual':
                from PIL import Image
                from ..asset.joints.partition_pixels import png
                with Image.open(BytesIO(raw)) as image:
                    alpha=image.getchannel('A').tobytes()
                    colored=bytes(v for a in alpha for v in ((220,35,55,210) if a else (0,0,0,0)))
                    overlay=png('RGBA',image.size,colored)
                overlay_url=_image_url(overlay,hashlib.sha256(overlay).hexdigest())
                diagnostic=f'<details><summary>高亮残余像素（诊断色，不是源图）</summary><svg viewBox="0 0 {w} {h}"><image href="{background}" width="{w}" height="{h}" opacity=".12"/><image href="{overlay_url}" x="{x}" y="{y}" width="{r-x}" height="{b-y}"/></svg></details>'
            panels.append(f'<section><h3>{label} · {qa["visible_pixel_counts"][code]} 像素</h3>'
                f'<svg viewBox="0 0 {w} {h}"><image href="{background}" width="{w}" height="{h}" opacity=".12"/>'
                f'<image href="{url}" x="{x}" y="{y}" width="{r-x}" height="{b-y}"/></svg>{diagnostic}</section>')
        cards.append(f'<article><h2>{escape(source["name"])}</h2><p>RGBA逐字节重建：通过；小组件：{len(qa["satellite_components"])} 个。</p><div>{"".join(panels)}</div></article>')
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'">
<title>无损组件分区</title><style>body{{max-width:1350px;margin:24px auto;padding:0 20px;font:16px/1.6 system-ui;background:#f5f7fa;color:#233548}}
article{{background:white;padding:16px;margin:20px 0;border:1px solid #ccd}}article div{{display:flex;flex-wrap:wrap}}section{{flex:1;min-width:260px}}svg{{width:100%}}
.notice{{background:#fff0cc;padding:16px}}</style><h1>无损组件分区</h1><p class="notice">左/右均为角色侧别候选。小组件按主要组件重心距离归属；
低alpha边缘按4连通最短距离传播，平局与孤立边缘保留于残余。透明像素RGB同样保留。像素无损不代表绑定正确；尚未生成权重。</p>{''.join(cards)}</html>'''
