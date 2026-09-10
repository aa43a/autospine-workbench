"""Explicit ordinary/wide sleeve target selection from exact saved ownership."""
from ..asset.planning.ordinary_sleeve import build, PROFILE
from ..asset.planning.ordinary_sleeve_validation import validate
from ..benchmark.mesh_storage import publish_mesh_report
from ..resolved_project import canonical_sha256


def prepare(source, garment, draft, skeleton, state_root):
    if garment['draft_sha256'] != canonical_sha256(draft):
        raise ValueError('sleeve_export_draft_mismatch')
    ordinary = {(row['layer_id'], row['component_id']) for row in draft['records']
                if not any(item['role'] == 'hanging_cloth' for item in row['assignments'])}
    if not ordinary:
        return source['records'], None, {}, {}
    report = build(garment, draft, skeleton)
    validate(report, skeleton, source=garment, draft=draft)
    digest = publish_mesh_report(state_root, 'project-component-partitions', report)
    by_key = {(row['layer_id'], row['component_id']): row for row in report['records']}
    old = {(row['layer_id'], row['component_id']): row for row in source['records']}
    rows, selections, metadata = [], {}, {}
    for mesh in garment['records']:
        key = mesh['layer_id'], mesh['component_id']
        if key in ordinary:
            row = by_key[key]
            selections[key] = report
            metadata[key] = dict(motion_profile=PROFILE, motion_source_sha256=digest)
        else:
            row = old.get(key, dict(layer_id=key[0], component_id=key[1], status='blocked',
                                   reason_codes=['sleeve_region_unavailable']))
            metadata[key] = dict(motion_profile='wide-sleeve-seven-v1', motion_source_sha256=canonical_sha256(source))
        rows.append(row)
    return rows, 'autospine.sleeve-export-report/v2', selections, metadata
