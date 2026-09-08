"""Build source-linked local review cards from captured official Runtime differences."""
import argparse
from hashlib import sha256
from html import escape
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw
from .artifacts import read_input
from .seam_candidate_hub import bundle_bytes
from .wing_spine_preview import encode
from ..asset.planning.residual_locations import locate, clusters
from ..asset.planning.wing_edge_ownership import decode, encode as png
from ..resolved_project import canonical_sha256


def box(points, size, pad):
    xs, ys = zip(*points)
    return [max(0, math.floor(min(xs))-pad), max(0, math.floor(min(ys))-pad),
            min(size[0], math.ceil(max(xs))+pad+1), min(size[1], math.ceil(max(ys))+pad+1)]


def build(capture, files):
    if capture['schema'] != 'autospine.residual-location-capture/v1' or capture['authority'] != 'none' or capture['production_authorized'] is not False:
        raise ValueError('residual_location_capture')
    if set(files) != set(capture['files']) or any(sha256(files[n]).hexdigest() != h for n, h in capture['files'].items()):
        raise ValueError('residual_location_file_changed')
    camera = capture['camera']; outputs = {}; rows = []; cards = []
    for row_index, row in enumerate(capture['rows']):
        source = decode(files[row['source_image']]); full = decode(files[row['full_image']]); without = decode(files[row['without_image']])
        if full.size != (camera['width'], camera['height']) or without.size != full.size:
            raise ValueError('residual_location_camera')
        points = locate(row, camera, source.size); groups = clusters(points)
        texel_set = sorted({tuple(t) for p in points if p['mapping'] for t in p['mapping']['texel_neighborhood']})
        alphas = [source.getpixel(t)[3] for t in texel_set]
        rows.append(dict(id=row['id'], tick=row['tick'], points=points, display_clusters=groups,
                         sampled_texel_count=len(texel_set), sampled_nonzero_texels=sum(a>0 for a in alphas),
                         sampled_max_alpha=max(alphas, default=0), sampled_alpha8_texels=sum(a>=8 for a in alphas)))
        for group_index, indices in enumerate(groups):
            group = [points[i] for i in indices]; prefix = f'row-{row_index}-region-{group_index}'
            screen = [[p['pixel'][0], camera['height']-1-p['pixel'][1]] for p in group]
            rect = box(screen, full.size, 12)
            original = full.crop(rect); hidden = without.crop(rect); marked = original.copy(); draw = ImageDraw.Draw(marked)
            for x, y in screen:
                draw.ellipse((x-rect[0]-2, y-rect[1]-2, x-rect[0]+2, y-rect[1]+2), outline=(255, 40, 30, 255))
            images = [('full', original, '完整画面'), ('without', hidden, '仅隐藏本层残余'), ('marked', marked, '差异采样位置')]
            texels = [t for p in group if p['mapping'] for t in p['mapping']['texel_neighborhood']]
            if texels:
                source_rect = box(texels, source.size, 6)
                images.append(('source', source.crop(source_rect), '原残余纹理邻域'))
                crop = source.crop(source_rect)
                amplified = Image.new('RGB', crop.size)
                amplified.putdata([(min(255, a*32),)*3 for a in crop.getchannel('A').tobytes()])
                images.append(('alpha', amplified.convert('RGBA'), 'alpha ×32 灰度诊断'))
                ox, oy = row['setup_vertices_xy'][0]
                origin = f'源纹理窗口 {source_rect}；原画布窗口左上 ({ox+source_rect[0]:g}, {oy+source_rect[1]:g})'
            else:
                source_rect = None; origin = '未映射到纹理；保留复核'
            plots = []
            for suffix, image, label in images:
                name = prefix+'-'+suffix+'.png'; outputs[name] = png(image)
                plots.append(f'<figure><img src="{name}"><figcaption>{label}</figcaption></figure>')
            exposed = sum(p['exposed'] for p in group)
            cards.append(f'<article><h2>{escape(row["id"])} · {row["tick"]}/60秒 · 局部 {group_index+1}</h2><p>{len(group)} 个采样，隐藏后降到 alpha 8 以下：{exposed}。{origin}</p><div class="grid">{"".join(plots)}</div></article>')
            rows[-1].setdefault('windows', []).append(dict(indices=indices, framebuffer_crop_top_left=rect, source_crop=source_rect))
    report = dict(schema='autospine.residual-source-locations/v1', source_capture_sha256=canonical_sha256(capture),
                  source_preview_sha256=capture['source_preview_sha256'], rows=rows, target_count=sum(len(r['points']) for r in rows),
                  mapped_count=sum(p['mapping'] is not None for r in rows for p in r['points']), cluster_count=len(cards),
                  display_group_radius_px=4, authority='none', production_authorized=False,
                  interpretation='bilinear_sampling_neighborhood_not_pixel_deletion_or_ownership', files={n: sha256(r).hexdigest() for n,r in outputs.items()})
    outputs['locations.json'] = encode(report)
    outputs['index.html'] = ('''<!doctype html><meta charset="utf-8"><title>残余差异 · 源纹理定位</title>
<style>body{font:16px/1.7 system-ui;margin:28px;background:#eef1f5;color:#243448}article{background:white;padding:18px;margin:20px 0}.grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr))}figure{margin:8px}img{image-rendering:pixelated;max-width:100%;width:100%;height:220px;object-fit:contain;background:var(--bg,#172033)}figcaption{text-align:center}</style>
<h1>残余差异 → 源纹理局部复核</h1><p>每组使用同一帧和同一相机，只隐藏指定源层残余。红圈是显示像素中心；源纹理显示其双线性采样邻域，不代表这些 texel 应删除。4px分组只为排版，未丢弃采样。</p>
<button onclick="document.documentElement.style.setProperty('--bg','#fff')">白底</button><button onclick="document.documentElement.style.setProperty('--bg','#172033')">深色背景</button>
<p><a href="locations.json">精确坐标与来源</a></p>'''+''.join(cards)).encode()
    return report, outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True); parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(); capture = read_input(args.capture)
    report, files = build(capture, bundle_bytes(args.capture.parent, capture['files']))
    for name, raw in files.items():
        path = args.output_dir/name
        if path.exists() and path.read_bytes() != raw:
            raise ValueError('residual_location_existing_changed')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, raw in files.items():
        (args.output_dir/name).write_bytes(raw)
    print(json.dumps({k: report[k] for k in ('target_count', 'mapped_count', 'cluster_count')}))


if __name__ == '__main__':
    main()
