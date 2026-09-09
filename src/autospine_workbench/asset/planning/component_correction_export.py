"""Publish a replayable, non-adopted local correction comparison."""
from html import escape
from .component_local_correction import build
from .component_mesh_review import render
from ...resolved_project import canonical_sha256
from ...benchmark.mesh_storage import publish_mesh_report, read_mesh_report, export_mesh


def export(state, output, source_document, source):
    document = build(source_document,source.skeleton)
    source.assert_current()
    digest = publish_mesh_report(state,'project-component-partitions',document)
    checked = read_mesh_report(state,'project-component-partitions',digest)
    if canonical_sha256(checked) != canonical_sha256(build(source_document,source.skeleton)):
        raise ValueError('component_correction_replay_mismatch')
    source.assert_current()
    export_mesh(output/f'{digest}.json',checked)
    overrides, rows = {}, []
    for row in checked['rows']:
        overrides[row['layer_id'],row['component_id']] = [dict(id='试验 '+p['id'],points=p['points'],qa=p['selected_qa']) for p in row['poses']]
        chosen = sum(p['selected'] for p in row['poses'])
        before = sum(p['before_qa']['inversions'] for p in row['poses'])
        after = sum(p['selected_qa']['inversions'] for p in row['poses'])
        rows.append(f'<tr><td>{escape(row["layer_id"])} / {escape(row["component_id"])}</td><td>{chosen}</td><td>{before} → {after}</td></tr>')
    table = '<h2>局部 corrective 试验</h2><p>只移动异常三角形附近的混合权重顶点；最大位移为最短骨长的 10%。绑定权重、UV、网格拓扑均保持不变。</p>'
    table += '<p>拖动时间轴或播放，在同一时刻切换原结果／局部修正。逐姿态插值是诊断，不是已完成的 Spine 动画。</p>'
    table += '<table border="1" cellpadding="8"><tr><th>区域</th><th>改善姿态数</th><th>翻转总数</th></tr>'+''.join(rows)+'</table>'
    table += f'<p><a href="{digest}.json">完整局部顶点与诊断</a> · <a href="transitions.html">权重对照</a></p>'
    from .component_temporal_export import export as export_temporal
    table += export_temporal(state,output,source_document,checked,source)
    page = render(source_document,source.skeleton,overrides).replace('<main>',table+'<main>')
    (output/'corrections.html').write_text(page,encoding='utf-8')
    from .component_fk_export import export as export_fk
    export_fk(state,output,source_document,checked,source)
    from .component_collar_export import export as export_collar
    export_collar(state,output,source_document,checked,source)
    print(f"{document['project_id']}: {sum(p['selected'] for r in checked['rows'] for p in r['poses'])} improved local pose candidates")
