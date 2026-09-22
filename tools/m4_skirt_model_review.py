"""Localize contradictory depth hypotheses; never change candidate draw order."""
import argparse
import html
import json
import math
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.spine43.seam_raster import mask, texture


def disagreements(plane, surface):
    for field in ('artifact_sha256', 'experiment_sha256', 'times'):
        if not plane.get(field) or plane[field] != surface.get(field):
            raise ValueError('skirt_comparison_identity_mismatch')
    def indexed(report):
        result = {}
        for row in report['rows']:
            if 'pair' not in row:
                continue
            key = (row['time'], tuple(row['pair']))
            if key in result:
                raise ValueError('skirt_comparison_duplicate_row')
            result[key] = row
        return result
    left, right = indexed(plane), indexed(surface)
    if left.keys() != right.keys():
        raise ValueError('skirt_comparison_missing_pair')
    opposite = {'uniform_front_proxy', 'uniform_back_proxy'}
    return [dict(time=k[0], pair=list(k[1]), plane=a['status'], surface=right[k]['status'])
            for k, a in left.items() if {a['status'], right[k]['status']} == opposite]


def run(plane_path, surface_path, output):
    import numpy as np
    from PIL import Image
    plane, surface = [json.loads(p.read_text(encoding='utf-8')) for p in (plane_path, surface_path)]
    rows = disagreements(plane, surface)
    if len(rows) > 32:
        raise ValueError('skirt_comparison_budget')
    store = AnimatedStore(Path('workspace'))
    evidence = json.loads(store.read_file(plane['experiment_sha256'], 'experiment.json'))
    if evidence['report']['candidate_bundle_sha256'] != plane['artifact_sha256']:
        raise ValueError('skirt_comparison_experiment_mismatch')
    job = evidence['parent']['job_id']
    player = f'http://127.0.0.1:8918/api/motions/{job}/view/experiments/{plane["experiment_sha256"]}/player.html'
    files = store.read(plane['artifact_sha256'])
    document = json.loads(files['skeleton.json'])
    slots = {s['name']: s for s in document['slots']}
    output.mkdir(parents=True, exist_ok=False)
    cards = []
    for i, row in enumerate(rows):
        points, _ = sample(document, 'external-motion', row['time'])
        pair = row['pair']
        meshes = [document['skins'][0]['attachments'][n][slots[n]['attachment']] for n in pair]
        vertices = [points[n][j] for n, m in zip(pair, meshes) for j in m['triangles']]
        x, y = math.floor(min(p[0] for p in vertices)), math.floor(min(-p[1] for p in vertices))
        w, h = math.ceil(max(p[0] for p in vertices))-x, math.ceil(max(-p[1] for p in vertices))-y
        if w*h > 4_000_000 or w*h <= 0:
            raise ValueError('skirt_comparison_raster_budget')
        masks = [mask(m, points[n], texture(files['images/'+m.get('path', slots[n]['attachment'])+'.png']),
                      [x, y, w, h]) >= 8 for n, m in zip(pair, meshes)]
        common = masks[0] & masks[1]
        yy, xx = np.nonzero(common)
        row['overlap_pixels'] = int(common.sum())
        row['player_url'] = player + '?time=' + str(row['time'])
        row['setup_order_front_slot'] = max(pair, key=lambda n: list(slots).index(n))
        row['overlap_screen_bounds'] = [int(xx.min()+x), int(yy.min()+y), int(xx.max()+x+1), int(yy.max()+y+1)] if len(xx) else None
        rgb = np.full((h, w, 3), [24, 34, 45], dtype=np.uint8)
        rgb[masks[0]] = [71, 171, 245]
        rgb[masks[1]] = [85, 193, 130]
        rgb[common] = [255, 180, 65]
        Image.fromarray(rgb).save(output / f'overlap-{i}.png')
        cards.append(f'<section><h2>{html.escape(str(pair))} · {row["time"]:.6f}s</h2>'
                     f'<p>躯干平面：{row["plane"]}；裙装曲面假设：{row["surface"]}。'
                     f'重叠 {row["overlap_pixels"]} 像素；原始顺序前方部件：{html.escape(row["setup_order_front_slot"])}。</p>'
                     f'<p><a href="{html.escape(row["player_url"], quote=True)}">打开精确候选的该时刻</a></p>'
                     f'<img src="overlap-{i}.png"></section>')
    report = dict(artifact_sha256=plane['artifact_sha256'], experiment_sha256=plane['experiment_sha256'],
                  authority='none', order_changed=False, scope='cpu_alpha_overlap_model_disagreement_not_visual_acceptance', rows=rows)
    (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>裙腿模型冲突定位</title>'
        '<style>body{background:#111c26;color:#eee;font:16px sans-serif;margin:24px}img{max-width:100%;max-height:700px}section{margin:32px 0}</style>'
        '<h1>裙腿模型冲突定位</h1><p>蓝：腿；绿：裙；橙：实际 alpha 重叠。'
        '这是同帧 CPU 区域定位，不是最终颜色渲染，不代表橙色区域需要改层。候选和绘制顺序未修改。</p>'
        + ''.join(cards), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('plane', 'surface', 'output'):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    run(a.plane, a.surface, a.output)
