"""Show explicit static-reference ownership without deleting or adopting pixels."""
from hashlib import sha256
from html import escape
from io import BytesIO
import json
from pathlib import PurePosixPath
from ...automation.storage_io import canonical_bytes


def build(files):
    from PIL import Image
    manifest = json.loads(files['character-manifest.json'])
    document = json.loads(files['skeleton.json'])
    attachments = document['skins'][0]['attachments']
    rows = []; outputs = {}; cards = []; links = {}; seen = set()
    for layer in manifest['layers']:
        for region in layer['regions']:
            if region['state'] != 'static_reference':
                continue
            name = region['region_id']
            if name in seen:
                raise ValueError('character_static_region_duplicate')
            seen.add(name)
            attachment = attachments[name][name]
            path = attachment.get('path', name)
            if not isinstance(path, str) or '\\' in path or PurePosixPath(path).is_absolute() \
                    or any(p in ('', '.', '..') for p in path.split('/')):
                raise ValueError('character_static_region_path')
            source = 'images/'+path+'.png'
            raw = files[source]
            with Image.open(BytesIO(raw)) as image:
                rgba = image.convert('RGBA'); alpha = rgba.getchannel('A')
                histogram = alpha.histogram(); bbox = alpha.getbbox()
                preview = rgba.crop(bbox) if bbox else Image.new('RGBA', (1, 1))
                encoded = BytesIO(); preview.save(encoded, format='PNG')
                size = list(rgba.size)
            index = len(rows); anchor = 'region-'+str(index); preview_name = anchor+'.png'
            outputs['static-regions/'+preview_name] = encoded.getvalue()
            links.setdefault(layer['layer_id'], []).append('static-regions/index.html#'+anchor)
            rows.append(dict(layer_id=layer['layer_id'], region_id=name, source_image=source,
                             source_sha256=sha256(raw).hexdigest(), image_size=size,
                             crop_bbox=list(bbox) if bbox else None, visible_pixels=sum(histogram[1:]),
                             alpha_at_least_8_pixels=sum(histogram[8:]), status='review_required'))
            cards.append(f'<section id="{anchor}"><h2>{escape(layer.get("name", layer["layer_id"]))}</h2>'
                         f'<p>{escape(name)} · 未绑定静态区域 · 可见像素 {sum(histogram[1:])}</p>'
                         f'<img src="{preview_name}" alt="未绑定区域纹理"><p>原纹理局部裁切，仅供归属定位；'
                         '不代表动画位置。请判断保留、绑定或修复；此页不会删除像素。</p></section>')
    report = dict(schema='autospine.static-region-review/v1', authority='none',
                  production_authorized=False, skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
                  manifest_sha256=sha256(files['character-manifest.json']).hexdigest(), rows=rows)
    outputs['static-regions/report.json'] = canonical_bytes(report)
    page = '<!doctype html><meta charset="utf-8"><title>未绑定区域定位</title><style>' \
           'body{background:#172330;color:#eee;font:16px sans-serif;margin:24px}section{margin:24px 0;padding:16px;border:1px solid #567}' \
           'img{max-width:90vw;max-height:65vh;background:repeating-conic-gradient(#354451 0 25%,#273440 0 50%) 0/24px 24px}' \
           '</style><h1>未绑定区域定位</h1><p>来自当前整角色包的静态参考，尚未完成归属处理。</p>'
    outputs['static-regions/index.html'] = (page+(''.join(cards) or '<p>没有未绑定静态区域。</p>')).encode()
    return outputs, links
