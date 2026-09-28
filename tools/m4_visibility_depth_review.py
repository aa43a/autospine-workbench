"""Join immutable GPU visibility and audited source-depth evidence for local review."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from PIL import Image
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.runtime_visibility_depth import build
from m4_region_surface_audit import verify


def run(visibility, surfaces, prior_review, output):
    if output.exists(): raise ValueError('output_exists')
    raw = (visibility/'report-controlled.json').read_bytes(); gpu = json.loads(raw)
    fixture_raw = (visibility/'fixture.json').read_bytes(); fixture = json.loads(fixture_raw)
    depth_raw = (surfaces/'report.json').read_bytes(); depth = json.loads(depth_raw)
    audit = json.loads((surfaces/'coverage-audit.json').read_bytes())
    prior = json.loads((prior_review/'report.json').read_bytes())
    if (gpu['fixture_sha256'] != sha256(fixture_raw).hexdigest()
            or gpu.get('negative_controls') != dict(order=True, image=True)
            or audit['report_sha256'] != sha256(depth_raw).hexdigest()
            or fixture['source_artifact_sha256'] != depth['source_artifact_sha256']
            or gpu['skeleton_sha256'] != depth['skeleton_sha256']
            or gpu['diagnostic_sha256'] != prior['diagnostic_sha256']
            or gpu['runtime_report_sha256'] != prior['runtime_report_sha256']):
        raise ValueError('visibility_depth_identity')
    if len(gpu['rows']) != len(fixture['rows']): raise ValueError('visibility_depth_frame_inventory')
    for actual, expected in zip(gpu['rows'], fixture['rows']):
        if (any(actual[k] != expected[k] for k in ('time', 'region', 'body', 'screenshot_sha256'))
                or [{k:p[k] for k in ('x','y','kind')} for p in actual['points']] != expected['points']):
            raise ValueError('visibility_depth_pixel_inventory')
    checks = []
    for region in depth['regions']:
        if Path(region).name != region or '/' in region or '\\' in region: raise ValueError('visibility_depth_path')
        data = (surfaces/(region+'.json')).read_bytes()
        if sha256(data).hexdigest() != audit['checkpoint_sha256'][region]: raise ValueError('visibility_depth_checkpoint')
        checks.extend(json.loads(data))
    first = depth['pairs'][0]
    times = sorted((r['time'], r['source_tick']) for r in checks if (r['arm'], r['body']) == (first['arm'], first['body']))
    coverage = verify(depth, checks, times)
    result = build(gpu['rows'], checks)
    result.update(visibility_sha256=sha256(raw).hexdigest(), surface_report_sha256=sha256(depth_raw).hexdigest(),
                  source_artifact_sha256=fixture['source_artifact_sha256'], skeleton_sha256=gpu['skeleton_sha256'],
                  coverage=coverage, runtime_version=gpu['runtime_version'])
    output.mkdir(parents=True, exist_ok=False); cards = []
    for index, row in enumerate(result['rows']):
        frame_index, frame = next((i, f) for i, f in enumerate(prior['frames'])
                                 if f['time'] == row['time'] and f['region'] == row['region'])
        if frame['screenshot_sha256'] != gpu['rows'][index]['screenshot_sha256']:
            raise ValueError('visibility_depth_same_frame_image')
        full_raw = (prior_review/f'{frame_index}-full.png').read_bytes()
        if sha256(full_raw).hexdigest() != frame['screenshot_sha256']: raise ValueError('visibility_depth_image')
        with Image.open(prior_review/f'{frame_index}-full.png') as image:
            crop = image.convert('RGBA').crop(frame['crop'])
        crop.save(output/f'{index}-runtime.png'); overlay = Image.new('RGBA', crop.size)
        for point in row['points']:
            color = (255,80,110,210) if point['status'] == 'opaque_blocker_proxy_conflict' else (255,185,60,180)
            x, y = point['x']-frame['crop'][0], point['y']-frame['crop'][1]
            if not 0 <= x < crop.width or not 0 <= y < crop.height: raise ValueError('visibility_depth_crop')
            overlay.putpixel((x, y), color)
        overlay.save(output/f'{index}-markers.png')
        counts = row['counts']
        cards.append(f'<section><h2>{row["time"]:g} 秒</h2><p>实际遮挡与代理深度冲突：{counts.get("opaque_blocker_proxy_conflict",0)}<br>'
                     f'手被遮住、深度未定：{counts.get("hidden_depth_unresolved",0)}</p>'
                     f'<div class="crop"><img src="{index}-runtime.png"><img class="markers" src="{index}-markers.png"></div></section>')
    (output/'report.json').write_bytes(canonical_bytes(result))
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>手部被遮挡定位</title>'
        '<style>body{background:#15212b;color:#edf2f7;font:16px system-ui;padding:24px}main{display:flex;flex-wrap:wrap;gap:24px}'
        'section{background:#263744;padding:16px}.crop{position:relative;line-height:0}.crop img{width:320px;image-rendering:pixelated}'
        '.markers{position:absolute;inset:0}.hide .markers{display:none}a{color:#7cceff}</style>'
        '<h1>手部被遮挡：实际覆盖与来源深度</h1><p>红色：实际不透明遮挡物与来源深度代理矛盾。橙色：隐藏已确认，但深度证据仍不足。</p>'
        '<p>红色不等于可以直接换层；前方还有裙片，必须同时解决覆盖关系。此页不通过候选，也不修改动画。</p>'
        '<label><input type="checkbox" checked onchange="document.body.classList.toggle(\'hide\',!this.checked)">显示定位</label>'
        '<p><a href="report.json">逐像素证据</a></p><main>'+''.join(cards)+'</main>', encoding='utf-8')
    print(json.dumps(result['counts']))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('visibility', 'surfaces', 'prior_review', 'output'): p.add_argument(key, type=Path)
    a = p.parse_args(); run(a.visibility, a.surfaces, a.prior_review, a.output)
