"""Read the frozen first ten and live catalog, with actionable workbench links."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import urlopen
from autospine_workbench.automation.cohort_intake import assess
from autospine_workbench.automation.storage_io import canonical_bytes


LABELS = dict(psd_variant_review_required='先核对 PSD 版本', project_selection_required='选择对应项目',
              source_matched_workflow_not_assessed='PSD 身份匹配；待检查完整工作流',
              asset_restore_required='在资产中心恢复项目', audit_source_verification_required='核对旧审计的 PSD 来源',
              psd_import_required='在资产中心导入 PSD')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path('docs/benchmark/manifest-frozen-v1.json'))
    parser.add_argument('--base-url', default='http://127.0.0.1:8918')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    origin = urlsplit(args.base_url)
    if (origin.scheme != 'http' or origin.hostname not in ('localhost', '127.0.0.1')
            or origin.path or origin.query or origin.fragment or origin.username or origin.password):
        parser.error('base URL must be a local workbench origin')
    with urlopen(args.base_url + '/api/asset-library', timeout=120) as response:
        catalog = response.read(32 << 20)
    manifest = args.manifest.read_bytes()
    report = assess(json.loads(manifest), json.loads(catalog))
    report.update(manifest_sha256=sha256(manifest).hexdigest(), catalog_sha256=sha256(catalog).hexdigest())
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'catalog.json').write_bytes(catalog)
    (args.output / 'manifest.json').write_bytes(manifest)
    (args.output / 'report.json').write_bytes(canonical_bytes(report))
    cards = []
    for row in report['characters']:
        links = []
        for p in row['exact_projects'] + row['audit_hints']:
            url = args.base_url + '/?project=' + quote(p['id'], safe='')
            links.append(f'<a href="{escape(url, quote=True)}">{escape(p["name"])}</a> ({escape(p["lifecycle"])})')
        sources = ', '.join(escape(c['path']) for c in row['psd_candidates'])
        cards.append(f'<tr><td>{escape(row["name"])}</td><td>{row["dataset_split"]}</td>'
                     f'<td>{LABELS[row["reason_code"]]}</td><td>{sources}</td><td>{" · ".join(links) or "—"}</td></tr>')
    html = '<!doctype html><meta charset="utf-8"><title>首批十角色准备清单</title>'
    html += '<style>body{font:16px system-ui;background:#12202b;color:#eef4f8;margin:32px}table{border-collapse:collapse;width:100%}td,th{padding:16px;border-bottom:1px solid #456;text-align:left}a{color:#7ddaff}</style>'
    html += '<h1>首批十角色准备清单</h1><p>这是只读盘点。来源匹配不等于绑定完成或动作通过；同名旧审计仅作为核对入口。</p>'
    html += '<p>冻结分组保持原样。曾用于开发或反复复核的角色，不能直接宣称为独立 holdout；需要另行核对使用记录。</p>'
    html += f'<p><a href="{escape(args.base_url, quote=True)}">打开工作台资产中心</a> · <a href="report.json">查看盘点数据</a></p>'
    html += '<table><tr><th>角色</th><th>冻结分组</th><th>下一步</th><th>PSD 候选</th><th>项目入口</th></tr>' + ''.join(cards) + '</table>'
    (args.output / 'index.html').write_text(html, encoding='utf-8')
    print(json.dumps(dict(total=report['total_characters'], exact=report['exact_active_single_source'])))


if __name__ == '__main__':
    main()
