"""Inspect a captured PNG without changing its pixels or asset authority."""
import argparse
from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

from PIL import Image, ImageDraw


def inspect(raw, expected):
    if sha256(raw).hexdigest() != expected:
        raise ValueError('framebuffer_image_identity_mismatch')
    with Image.open(BytesIO(raw)) as image:
        rgba = image.convert('RGBA')
    histogram = Counter(rgba.getchannel('A').tobytes())
    summary = {'transparent': histogram[0], 'alpha_1_to_7': sum(histogram[a] for a in range(1, 8)),
               'alpha_8_to_254': sum(histogram[a] for a in range(8, 255)), 'opaque': histogram[255]}
    images = {}
    for name, color in [('black', (0, 0, 0)), ('white', (255, 255, 255)),
                        ('slate', (38, 52, 66))]:
        background = Image.new('RGBA', rgba.size, color + (255,))
        images[name] = Image.alpha_composite(background, rgba).convert('RGB')
    checker = Image.new('RGBA', rgba.size, (50, 60, 70, 255))
    draw = ImageDraw.Draw(checker)
    for y in range(0, rgba.height, 24):
        for x in range(0, rgba.width, 24):
            if (x // 24 + y // 24) % 2:
                draw.rectangle((x, y, x + 23, y + 23), fill=(70, 80, 90, 255))
    images['checker'] = Image.alpha_composite(checker, rgba).convert('RGB')
    # On black, each RGB channel cannot contribute more than the texel alpha.
    low_alpha = rgba.getchannel('A').point(lambda a: 255 if 0 < a < 8 else 0)
    black = images['black']; peaks = []
    for channel in black.split():
        masked = Image.composite(channel, Image.new('L', rgba.size), low_alpha)
        peaks.append(masked.getextrema()[1])
    report = dict(schema='autospine.framebuffer-alpha-inspection/v1', authority='none',
                  production_authorized=False, source_sha256=expected, image_size=list(rgba.size),
                  alpha_histogram={str(k): histogram[k] for k in sorted(histogram)},
                  counts=summary, low_alpha_black_rgb_peak=peaks,
                  scope='saved_straight_rgba_png_composited_over_opaque_backgrounds',
                  limitation='not_a_new_runtime_capture_or_visibility_approval; no_pixels_removed')
    return report, images


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report, images = inspect(args.image.read_bytes(), args.expected_sha256)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, image in images.items():
        image.save(args.output / (name + '.png'))
    (args.output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    labels = {'checker': '棋盘背景', 'slate': '深色背景', 'white': '白色背景', 'black': '黑色背景'}
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>捕获帧透明度核对</title>
<style>body{background:#17222d;color:#eef5ff;font:16px system-ui;max-width:1100px;margin:auto;padding:24px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}img{width:100%;height:auto}
a{color:#7de0ff}figure{margin:0}</style><h1>捕获帧透明度核对</h1>
<p>使用同一张官方捕获 PNG，按其真实透明度合成背景。没有删除像素，没有修改绑定。</p>
<p>这些是不透明的诊断图，可避免查看器忽略 PNG 透明度而夸大散点。不代表新的 Runtime 捕获或视觉验收。</p>'''
    page += '<p>透明度 1–7/255 的像素数：' + str(report['counts']['alpha_1_to_7']) + '</p>'
    page += '<div class="grid">' + ''.join('<figure><h2>' + labels[name] + '</h2><img src="' +
             name + '.png" alt="' + labels[name] + '"></figure>' for name in labels) + '</div>'
    page += '<p><a href="report.json">来源摘要与完整透明度统计</a></p></html>'
    (args.output / 'index.html').write_text(page, encoding='utf-8')
    print(json.dumps(report['counts']))


if __name__ == '__main__':
    main()
