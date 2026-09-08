"""Source/ownership overlays distinguish retained residual from bone support."""
from html import escape
from io import BytesIO
from ..asset.joints.partition_pixels import png
from .semantic_view import _image_url
import hashlib


def render(doc,files):
    from PIL import Image
    cards=[]
    for layer in doc['layers']:
        source=files[layer['texture_ref']];mask=files[layer['ownership_ref']]
        with Image.open(BytesIO(mask)) as image:w,h=image.size;owners=image.tobytes()
        overlay=png('RGBA',(w,h),b''.join({1:b'\x16\xa3\xa0\x70',2:b'\xd1\x66\x21\x70',3:b'\xdc\x31\x8a\x70'}[o] for o in owners))
        # Transparent source pixels stay invisible even when they retain hidden RGB.
        with Image.open(BytesIO(source)) as image:alpha=image.tobytes()[3::4]
        pixels=bytearray()
        with Image.open(BytesIO(overlay)) as image:pixels=bytearray(image.tobytes())
        for i,a in enumerate(alpha):
            if not a:pixels[i*4+3]=0
        overlay=png('RGBA',(w,h),pixels)
        source_url=_image_url(source,hashlib.sha256(source).hexdigest());mask_url=_image_url(overlay,hashlib.sha256(overlay).hexdigest())
        points=[];labels=[];x,y,_,_=layer['bbox']
        colors=['#1557b0','#dc7a11','#932faa']
        for part in layer['partitions']:
            geometry=part['geometry']
            for vertex,weights in zip(geometry['vertices_xy'],geometry['weights']):
                index=max(range(len(weights)),key=lambda i:weights[i]['weight'])
                points.append(f'<circle cx="{vertex[0]-x}" cy="{vertex[1]-y}" r="1.3" fill="{colors[index]}"/>')
            labels.append(f'<li>{escape(part["id"])}：{escape(" → ".join(part["bone_ids"]))}；过渡顶点 {part["weight_support"]["transition_vertex_count"]}；{escape(part["status"])}。</li>')
        cards.append(f'<article><h2>{escape(layer["layer_id"])}</h2><p>一张源纹理 · 两个运动分区 · 残余 {layer["residual"]["visible_pixels"]} 像素保留未绑定。</p>'
            f'<div class="views"><figure><figcaption>源纹理</figcaption><svg viewBox="0 0 {w} {h}"><image href="{source_url}" width="{w}" height="{h}"/></svg></figure>'
            f'<figure><figcaption>左右归属与残余</figcaption><svg viewBox="0 0 {w} {h}"><image href="{source_url}" width="{w}" height="{h}"/><image href="{mask_url}" width="{w}" height="{h}"/></svg></figure>'
            f'<figure><figcaption>区域内主导骨影响</figcaption><svg viewBox="0 0 {w} {h}"><image href="{source_url}" width="{w}" height="{h}" opacity=".3"/>{"".join(points)}</svg></figure></div><ul>{"".join(labels)}</ul></article>')
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+\
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'; base-uri \'none\'">'+\
        '<title>共享纹理分区 v2</title><style>body{max-width:1200px;margin:24px auto;padding:0 20px;font:16px/1.6 system-ui;background:#f5f7fa;color:#233548}article{background:white;padding:20px;margin:20px 0}.views{display:grid;grid-template-columns:repeat(3,1fr)}figure{margin:8px}svg{width:100%;max-height:560px}.notice{background:#fff0cc;padding:16px}</style>'+\
        '<h1>共享源纹理 · 分区与权重 v2</h1><p class="notice">青色为左分区，橙色为右分区，粉色为未解决残余。权重图蓝／橙／紫分别表示骨链第1／2／3根骨的主导影响，完整混合权重保存在工件中。'+\
        'RGBA重建通过不表示绑定已批准；Spine尚未实现共享纹理的ownership裁剪，直接复用源纹理可能显示其它分区像素，因此目标导出保持阻塞。</p>'+''.join(cards)+'</html>'
