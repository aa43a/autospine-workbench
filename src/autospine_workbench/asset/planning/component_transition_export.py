"""Replay a bounded weight experiment and expose baseline comparison."""
from html import escape
from .component_weight_transition import build, _score
from .component_mesh_review import render
from ...benchmark.mesh_storage import publish_mesh_report, read_mesh_report, export_mesh
from ...resolved_project import canonical_sha256


def export(state, output, baseline, source, entries, correction=False):
    document = build(baseline, source.skeleton, entries)
    source.assert_current()
    digest = publish_mesh_report(state, 'project-component-partitions', document)
    checked = read_mesh_report(state, 'project-component-partitions', digest)
    if canonical_sha256(checked) != canonical_sha256(build(baseline, source.skeleton, entries)):
        raise ValueError('component_transition_replay_mismatch')
    source.assert_current()
    export_mesh(output / f'{digest}.json', checked)
    rows = []
    for c in checked['comparisons']:
        before, after = _score(c['baseline_qa']), _score(c['selected_qa'])
        rows.append(f'<tr><td>{escape(c["layer_id"])} / {escape(c["component_id"])}</td>'
                    f'<td>{before[0]} → {after[0]}</td><td>{before[1]} → {after[1]}</td>'
                    f'<td>{c["selected_factor"] if c["selected_factor"] else "保留原权重"}</td></tr>')
    table = '<h2>原结果与局部过渡试验对照</h2><p>失败姿态数 / 各姿态翻转数之和；试验选择不代表采用。原通过姿态不得新增失败。</p>'
    table += '<table border="1" cellpadding="8"><tr><th>区域</th><th>失败姿态</th><th>翻转总数</th><th>半径倍率</th></tr>' + ''.join(rows) + '</table>'
    table += f'<p><a href="{digest}.json">完整试验数据</a> · <a href="mesh.html">原网格对照</a></p>'
    page = render(checked, source.skeleton).replace('<main>', table+'<main>')
    (output / 'transitions.html').write_text(page, encoding='utf-8')
    print(f"{document['project_id']}: {sum(c['selected_factor'] is not None for c in checked['comparisons'])} improved transition experiments")
    if correction:
        from .component_correction_export import export as export_correction
        export_correction(state,output,checked,source)
