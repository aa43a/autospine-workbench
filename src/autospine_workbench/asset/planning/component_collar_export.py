"""Publish local collar trials with FK playback of the non-regressing subset."""
from html import escape
from .component_collar import build
from .component_mesh_review import render
from ...resolved_project import canonical_sha256
from ...benchmark.mesh_storage import publish_mesh_report,read_mesh_report,export_mesh


def export(state,output,document,correction,source):
    result=build(document,correction,source.skeleton)
    source.assert_current();digest=publish_mesh_report(state,'project-component-partitions',result)
    checked=read_mesh_report(state,'project-component-partitions',digest)
    if canonical_sha256(checked)!=canonical_sha256(build(document,correction,source.skeleton)):
        raise ValueError('collar_replay_mismatch')
    source.assert_current();export_mesh(output/f'{digest}.json',checked)
    rows=[]
    for c in checked['comparisons']:
        after=c['score_after'] if c['selected'] else c['score_before']
        rows.append(f'<tr><td>{escape(c["layer_id"])} / {escape(c["bone_id"])}</td>'
                    f'<td>{c["score_before"][0]} → {after[0]}</td><td>{c["score_before"][1]} → {after[1]}</td>'
                    f'<td>{"试验改善" if c["selected"] else "保留此前结果"}</td></tr>')
    table='<h2>关节邻域局部修正</h2><p>允许异常三角形邻接的一圈刚性顶点参与。肘/膝范围≤相邻短骨长55%；腕/踝范围≤前臂/小腿骨长45%。位移≤对应骨长15%，从原FK位置计量。保持原纹理、权重与拓扑。</p>'
    table+='<p>播放中的「原结果」是未加corrective的FK，「局部修正」包含此前修正与本次通过回归的试验。表格比较的是本次前后。</p>'
    table+='<table border="1" cellpadding="6"><tr><th>关节</th><th>失败采样</th><th>翻转总数</th><th>状态</th></tr>'+''.join(rows)+'</table>'
    table+=f'<p><a href="{digest}.json">完整试验数据</a> · <a href="fk.html">此前FK修正对照</a></p>'
    overrides={(r['layer_id'],r['component_id']):r['poses'] for r in checked['rows']}
    (output/'collar.html').write_text(render(document,source.skeleton,overrides,fk=True).replace('<main>',table+'<main>'),encoding='utf-8')
    print(f"Collar: {sum(c['selected'] for c in checked['comparisons'])} improved tracks")
    from .component_collar_keys_export import export as export_keys
    export_keys(state,output,document,checked,source)
