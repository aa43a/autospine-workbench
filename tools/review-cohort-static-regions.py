"""Collect immutable candidate residuals for a source-bound human review."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.static_region_review import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--state-root', type=Path, default=Path('workspace'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = args.snapshot.read_bytes()
    snapshot = json.loads(raw)
    if snapshot.get('schema') != 'autospine.cohort-workflow/v1':
        raise ValueError('cohort_snapshot_schema_invalid')
    store = AnimatedStore(args.state_root)
    rows = []; cards = []
    args.output.mkdir(parents=True, exist_ok=True)
    for character in snapshot['characters']:
        digest = character.get('artifact_sha256')
        if character.get('completed') or not digest:
            continue
        files = store.read(digest)
        outputs, _ = build(files)
        report = json.loads(outputs['static-regions/report.json'])
        folder = args.output / digest
        for name, content in outputs.items():
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        for index, region in enumerate(report['rows']):
            # Keep high-alpha evidence visible; this is not an exclusion policy.
            classification = ('empty' if region['visible_pixels'] == 0 else
                              'low_alpha_only' if region['alpha_at_least_8_pixels'] == 0
                              else 'visible_content_requires_ownership')
            row = dict(region, project_id=character['project_id'],
                       name=character['name'], job_id=character['job_id'],
                       artifact_sha256=digest, classification=classification)
            rows.append(row)
            href = digest + '/static-regions/index.html#region-' + str(index)
            label = {'empty': '空纹理', 'low_alpha_only': '仅低透明度像素',
                     'visible_content_requires_ownership': '含实际可见内容'}[classification]
            cards.append('<tr><td>' + escape(character['name']) + '</td><td>'
                         + escape(region['region_id']) + '</td><td>'
                         + str(region['visible_pixels']) + '</td><td>'
                         + str(region['alpha_at_least_8_pixels']) + '</td><td>'
                         + label + '</td><td><a href="' + href + '">查看原图 / 增强定位</a></td></tr>')
    result = dict(schema='autospine.cohort-static-review/v1', authority='none',
                  production_authorized=False, snapshot_sha256=sha256(raw).hexdigest(),
                  scope='snapshot_candidates_not_live_selection', rows=rows)
    args.output.joinpath('report.json').write_bytes(canonical_bytes(result))
    page = ('<!doctype html><meta charset="utf-8"><title>整角色残余集中复核</title>'
            '<style>body{background:#172330;color:#eee;font:16px sans-serif;margin:32px}'
            'table{border-collapse:collapse}td,th{padding:12px;border:1px solid #567}'
            'a{color:#8dd9ff}</style><h1>整角色残余集中复核</h1>'
            '<p>来自固定候选快照。仅低透明度不等于可以删除；此页不修改纹理或确认记录。</p>'
            '<p>先查看正常透明度，再按需增强定位。含可见内容的区域需判断归属，不能统一排除。'
            '候选更新后须重新生成本页。</p><table><tr><th>角色</th><th>区域</th>'
            '<th>非零 alpha 像素</th><th>alpha ≥ 8 像素</th><th>分类</th><th>证据</th></tr>'
            + ''.join(cards) + '</table>')
    args.output.joinpath('index.html').write_text(page, encoding='utf-8')
    print(json.dumps(dict(regions=len(rows), low_alpha_only=sum(
        row['classification'] == 'low_alpha_only' for row in rows), empty=sum(
        row['classification'] == 'empty' for row in rows)), ensure_ascii=False))


if __name__ == '__main__':
    main()
