"""Export an exact-source visual proposal; never writes authoring decisions."""
import argparse
import hashlib
import html
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw

from autospine_workbench.automation.animated_inputs import load_inputs
from autospine_workbench.project_store import ProjectStore


def export(source, project, bindings, skirts, output):
    layers = {row['layer_id']: row for row in source.candidate['layers']}
    options = {row['layer_id']: {o['id']: o for o in row['options']}
               for row in source.bindings['bindings']}
    selections = [(key, option) for key, option in bindings]
    selections += [(key, None) for key in skirts]
    ids = [key for key, _ in selections]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError('Select distinct layers')
    rows = []
    for key, option in selections:
        if key not in layers or (option is not None and option not in options[key]):
            raise ValueError('Unknown layer or binding option: ' + key)
        layer = layers[key]
        if option is None and layer['name'] not in ('bottomwear', 'bottomwear-front'):
            raise ValueError('Layer is not supported by the skirt candidate profile')
        raw = source.images[key]
        if hashlib.sha256(raw).hexdigest() != layer['image_sha256']:
            raise ValueError('Layer image identity mismatch')
        rows.append(dict(layer_id=key, layer_name=layer['name'],
                         image_sha256=layer['image_sha256'], bbox=layer['bbox'],
                         option_id=option,
                         bone_ids=options[key][option]['bone_ids'] if option else [],
                         skirt_profile=None if option else 'reviewed-torso-waist-v2',
                         status='proposal_not_approved'))
    source.assert_current()
    output.mkdir(parents=True, exist_ok=True)
    composite = Image.open(io.BytesIO(source.composite)).convert('RGBA')
    cards = []
    for row in rows:
        key = row['layer_id']
        raw = source.images[key]
        (output / (key + '.png')).write_bytes(raw)
        context = Image.new('RGBA', composite.size, '#263442')
        context.alpha_composite(composite)
        draw = ImageDraw.Draw(context)
        draw.rectangle(row['bbox'], outline='#ffca63', width=4)
        for bone in source.skeleton['bones']:
            if bone['id'] in row['bone_ids']:
                draw.line([tuple(bone['head_xy']), tuple(bone['tail_xy'])],
                          fill='#36deff', width=5)
        context.thumbnail((640, 640))
        context.save(output / (key + '-context.png'))
        suggestion = ('刚性跟随 ' + ', '.join(row['bone_ids']) if row['option_id'] else
                      '腰部固定，裙摆使用独立辅助骨链；生成后另做动作验收')
        cards.append(f'<article id="{key}"><h2>{html.escape(row["layer_name"])}'
                     f' <small>{key}</small></h2><p>{html.escape(suggestion)}</p>'
                     f'<div class="images"><figure><img src="{key}-context.png" '
                     'alt="整角色位置与目标骨骼"><figcaption>黄色框为源图层位置，青色为目标骨骼</figcaption>'
                     f'</figure><figure><img src="{key}.png" alt="独立源图层">'
                     '<figcaption>独立源图层（完整透明边界保留）</figcaption></figure></div></article>')
    proposal = dict(schema='autospine.character-binding-review-proposal/v1',
                    authority='none', production_authorized=False, project_id=project,
                    source_addresses=source.source_addresses, rows=rows)
    (output / 'proposal.json').write_text(json.dumps(proposal, ensure_ascii=False, indent=2),
                                         encoding='utf-8')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>剩余图层集中复核</title>
<style>body{background:#111c27;color:#e7eff7;font:16px system-ui;margin:24px auto;max-width:1100px;padding:0 16px}
article{background:#1c2c3b;border:1px solid #476074;border-radius:10px;padding:18px;margin:22px 0}
.images{display:grid;grid-template-columns:1fr 1fr;gap:16px}figure{margin:0;min-width:0}
img{width:100%;height:400px;object-fit:contain;background:repeating-conic-gradient(#334555 0 25%,#293948 0 50%) 0/24px 24px}
figcaption,small{color:#b9c9d8}a{color:#72d6ff}nav{display:flex;gap:15px;flex-wrap:wrap}
@media(max-width:650px){.images{grid-template-columns:1fr}img{height:300px}}</style>
<h1>剩余图层集中复核</h1><p>这些是待确认方案。此页不修改项目，不生成已复核决定。</p>
<p>发层先随头部刚性运动，不包含头发物理；裙装仅确认候选方向，不能代替视觉验收。</p>'''
    page += '<nav>' + ''.join(f'<a href="#{r["layer_id"]}">{html.escape(r["layer_name"])}</a>'
                             for r in rows) + '</nav>'
    page += ''.join(cards) + '<p><a href="proposal.json">查看确切来源与方案记录</a></p></html>'
    source.assert_current()
    (output / 'index.html').write_text(page, encoding='utf-8')
    return proposal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--state-root', type=Path, required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--binding', action='append', default=[], metavar='LAYER=OPTION')
    parser.add_argument('--skirt', action='append', default=[], metavar='LAYER')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    pairs = []
    for value in args.binding:
        key, sep, option = value.partition('=')
        if not sep or not key or not option:
            parser.error('--binding requires LAYER=OPTION')
        pairs.append((key, option))
    with load_inputs(ProjectStore(args.workspace, args.state_root), args.project) as source:
        result = export(source, args.project, pairs, args.skirt, args.output)
    print(json.dumps({'layers': len(result['rows']), 'authority': 'none',
                      'view': str(args.output / 'index.html')}))


if __name__ == '__main__':
    main()
