"""Export actual weighted-region mappings from one verified character bundle."""
import argparse
from html import escape
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.binding_inventory import inspect


def export(store, digest, output):
    files = store.read(digest)
    manifest = json.loads(files['character-manifest.json'])
    skeleton = json.loads(files['skeleton.json'])
    inventory = inspect(skeleton, manifest['layers'])
    layers = {row['layer_id']: row for row in manifest['layers']}
    attachments = skeleton['skins'][0]['attachments']
    output.mkdir(parents=True, exist_ok=True)
    cards = []
    for index, row in enumerate(inventory['regions']):
        region = row['region_id']
        attachment = attachments[region][region]
        image = files['images/' + attachment.get('path', region) + '.png']
        image_name = f'region-{index}.png'
        (output / image_name).write_bytes(image)
        name = layers[row['layer_id']].get('name', row['layer_id'])
        entries = ''.join(
            '<tr><td>' + escape(item['bone']) + '</td><td>'
            + str(item['vertex_count']) + '</td><td>'
            + f'{item["min_weight"]:.3f}–{item["max_weight"]:.3f}' + '</td></tr>'
            for item in row['influences'])
        cards.append(
            f'<article id="region-{index}"><h2>{escape(name)}</h2>'
            f'<p>{escape(row["layer_id"])} · {escape(region)}</p>'
            f'<img src="{image_name}" alt="有效区域原纹理">'
            '<table><thead><tr><th>实际驱动骨骼</th><th>影响顶点数</th>'
            '<th>权重范围</th></tr></thead><tbody>' + entries + '</tbody></table></article>')
    report = dict(artifact_sha256=digest, authority='none', production_authorized=False,
                  binding_inventory=inventory)
    (output / 'inventory.json').write_bytes(canonical_bytes(report))
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>实际骨骼映射复核</title><style>
body{font:16px system-ui;background:#15212d;color:#edf2f7;max-width:1050px;margin:24px auto;padding:16px}
article{border:1px solid #587084;padding:20px;margin:20px 0;border-radius:10px}
img{max-width:100%;height:260px;object-fit:contain;background:repeating-conic-gradient(#344654 0 25%,#273642 0 50%) 0/20px 20px}
table{border-collapse:collapse;width:100%;margin-top:12px}td,th{text-align:left;padding:8px;border-bottom:1px solid #456}
p{overflow-wrap:anywhere}a{color:#80d9ff}</style>
<h1>实际骨骼映射复核</h1><p>从当前候选的顶点权重读取；不是仅根据名称推测。
只展示有效加权区域。确认归属不代替动作、连接和遮挡的视觉验收。</p>'''
    page += '<p>候选：' + escape(digest) + '</p>' + ''.join(cards)
    page += '<p><a href="inventory.json">查看精确映射记录</a></p></html>'
    (output / 'index.html').write_text(page, encoding='utf-8')
    return len(inventory['regions'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root', type=Path, required=True)
    parser.add_argument('--character', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    count = export(AnimatedStore(args.state_root), args.character, args.output)
    print(json.dumps(dict(regions=count, authority='none', view=str(args.output / 'index.html'))))
