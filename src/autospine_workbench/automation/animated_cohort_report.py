"""Deterministic cohort diagnostics, separate from approval and runtime evidence."""
from collections import Counter
from html import escape
from pathlib import Path

from ..resolved_project import canonical_sha256
from ..manifest_artifacts import require_safe_token, require_sha256
from .storage_io import directory, publish_document, read_document

SCHEMA = 'autospine.animated-cohort/v1'


def summarize(rows):
    if type(rows) is not list or len(rows) > 40:
        raise ValueError('cohort_case_limit')
    seen, reasons = set(), set()
    for row in rows:
        require_safe_token(row['project_id'], 'Project')
        if row['clip'] not in {'limb-flex-15', 'limb-flex-30'} or type(row['preview_available']) is not bool:
            raise ValueError('cohort_case_invalid')
        require_sha256(row['expected_resolved_sha256'], 'Source')
        key = (row['project_id'], row['clip'])
        if key in seen:
            raise ValueError('cohort_duplicate_case')
        seen.add(key)
        if row['status'] not in {'needs_review', 'blocked', 'failed', 'canceled'}:
            raise ValueError('cohort_case_invalid')
        if row['preview_available'] and (row['status'] != 'needs_review' or not row.get('run_id')):
            raise ValueError('cohort_preview_invalid')
        if row['preview_available']:
            require_sha256(row['bundle_sha256'], 'Preview')
            if row['source_addresses'].get('resolved_project_sha256') != row['expected_resolved_sha256']:
                raise ValueError('cohort_source_mismatch')
        for item in row['review_items']:
            reasons.add((row['project_id'], item.get('layer_id'), item['reason_code']))
        if row.get('reason_code'):
            reasons.add((row['project_id'], None, row['reason_code']))
    counts = Counter(reason for _, _, reason in reasons)
    return dict(projects=len({row['project_id'] for row in rows}), cases=len(rows),
                previews=sum(row['preview_available'] for row in rows),
                unavailable=sum(not row['preview_available'] for row in rows),
                reasons=[dict(reason_code=key, affected_project_layer_pairs=count)
                         for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))])


def build_report(rows):
    return dict(schema=SCHEMA, authority='none', production_authorized=False,
                runtime_status='not_evaluated', independent_gt=False,
                annotation_time_status='not_measured', rows=rows, summary=summarize(rows))


def validate_report(value):
    if (set(value) != set(build_report([])) or value != build_report(value['rows'])):
        raise ValueError('cohort_report_invalid')
    return value


def publish_report(output, report):
    validate_report(report)
    digest = canonical_sha256(report)
    folder = directory(Path(output).absolute() / digest, create=True)
    publish_document(folder / 'report.json', report, staging=folder / 'staging')
    if read_document(folder / 'report.json') != report:
        raise ValueError('cohort_report_conflict')
    from .animated_store import _publish_bytes
    _publish_bytes(folder / 'index.html', render_report(report).encode('utf-8'))
    return digest, folder


def read_report(path):
    path = Path(path)
    value = validate_report(read_document(path))
    if path.parent.name != canonical_sha256(value):
        raise ValueError('cohort_report_address_mismatch')
    return value


def render_report(report):
    validate_report(report)
    rows = []
    for row in report['rows']:
        summary = row['summary']
        cells = [row['project_id'], row['clip'], '可预览／待复核' if row['preview_available'] else row['status'],
                 summary.get('mesh_layers', 0), summary.get('context_layers', 0),
                 ', '.join(summary.get('rejected_mesh_layers', [])) or '—',
                 ', '.join(sorted({item['reason_code'] for item in row['review_items']})) or row.get('reason_code') or '—']
        rows.append('<tr>' + ''.join('<td>' + escape(str(value)) + '</td>' for value in cells) + '</tr>')
    reasons = ''.join('<li>' + escape(row['reason_code']) + ': ' + str(row['affected_project_layer_pairs']) + '</li>'
                      for row in report['summary']['reasons'])
    return ('<!doctype html><html lang="zh"><meta charset="utf-8"><title>跨角色动画验收</title>'
            '<style>body{font:15px system-ui;background:#121b28;color:#e3edf5;margin:32px}'
            'table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #456;text-align:left}'
            'td:last-child{max-width:460px;overflow-wrap:anywhere}a{color:#7dd3fc}</style>'
            '<h1>跨角色动画候选验收</h1><p>关节复核后的两组屈伸检查。可预览不代表完整角色通过；Mesh 数含单骨分区。</p>'
            '<p>官方 Runtime 未在本报告评估；人工耗时未测量；辅助标注不是独立 GT。后续编辑会使本快照过期。</p>'
            '<table><tr><th>项目</th><th>动作</th><th>状态</th><th>Mesh</th><th>刚性上下文</th><th>几何拒绝</th><th>异常</th></tr>'
            + ''.join(rows) + '</table><h2>异常频次（同角色／图层跨动作去重）</h2><ul>' + reasons + '</ul>'
            '<p><a href="report.json">精确运行身份与完整报告</a></p></html>')
