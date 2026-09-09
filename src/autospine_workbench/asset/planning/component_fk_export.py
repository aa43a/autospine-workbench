"""Paired FK and vertex-interpolation evidence with an FK timeline."""
from html import escape
from .component_fk_qa import build
from .component_temporal_qa import passed
from .component_mesh_review import render
from ...resolved_project import canonical_sha256
from ...benchmark.mesh_storage import publish_mesh_report,read_mesh_report,export_mesh


def export(state,output,document,correction,source):
    result=build(document,correction,source.skeleton)
    source.assert_current()
    digest=publish_mesh_report(state,'project-component-partitions',result)
    checked=read_mesh_report(state,'project-component-partitions',digest)
    if canonical_sha256(checked)!=canonical_sha256(build(document,correction,source.skeleton)):
        raise ValueError('component_fk_replay_mismatch')
    source.assert_current();export_mesh(output/f'{digest}.json',checked)
    rows=[]
    for row in checked['rows']:
        counts=[sum(not passed(t[k]) for t in row['ticks']) for k in ('linear','before','after')]
        rows.append(f'<tr><td>{escape(row["layer_id"])} / {escape(row["bone_id"])}</td>'
                    f'<td>{counts[0]}</td><td>{counts[1]} → {counts[2]}</td><td>{row["new_failure_count"]}</td></tr>')
    table='<h2>真实旋转插值对照</h2><p>线性顶点插值会沿弦运动；本页按骨骼角度计算 FK，并插值画布空间 corrective 偏移。尚未转换为 Spine deform。</p>'
    table+='<table border="1" cellpadding="6"><tr><th>区域/关节</th><th>顶点线性失败</th><th>FK 原→修正失败</th><th>修正新增失败</th></tr>'+''.join(rows)+'</table>'
    table+=f'<p><a href="{digest}.json">FK 检查数据</a> · <a href="corrections.html">顶点线性对照</a></p>'
    overrides={(r['layer_id'],r['component_id']):r['poses'] for r in correction['rows']}
    page=render(document,source.skeleton,overrides,fk=True).replace('<main>',table+'<main>')
    (output/'fk.html').write_text(page,encoding='utf-8')
    print(f"FK: {sum(r['interpolation_disagreements'] for r in checked['rows'])} interpolation disagreements; {sum(r['new_failure_count'] for r in checked['rows'])} new failures")
