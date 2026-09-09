"""Individual key regression evidence and updated FK playback."""
from html import escape
from .component_collar_keys import build,score
from .component_mesh_review import render
from ...resolved_project import canonical_sha256
from ...benchmark.mesh_storage import publish_mesh_report,read_mesh_report,export_mesh


def export(state,output,document,collar,source):
    result=build(document,collar,source.skeleton)
    source.assert_current();digest=publish_mesh_report(state,'project-component-partitions',result)
    checked=read_mesh_report(state,'project-component-partitions',digest)
    if canonical_sha256(checked)!=canonical_sha256(build(document,collar,source.skeleton)):
        raise ValueError('collar_keys_replay_mismatch')
    source.assert_current();export_mesh(output/f'{digest}.json',checked)
    rows=[]
    for c in checked['comparisons']:
        a,b=score(c['before']),score(c['after'])
        rejected=[t for t in c['trials'] if not t['selected']]
        details='; '.join(f"{t['key_id']}：新增失败{t['new_failure_times']}，新增翻转{t['new_inversion_times']}" for t in rejected)
        rows.append(f'<tr><td>{escape(c["layer_id"])} / {escape(c["bone_id"])}</td><td>{a[0]} → {b[0]}</td>'
                    f'<td>{a[1]} → {b[1]}</td><td>{escape(details) or "无被拒绝的局部关键姿态"}</td></tr>')
    table='<h2>逐关键姿态的局部修正</h2><p>从此前关节邻域候选继续，每加入一个关键姿态均重跑33点FK轨道，拒绝新增失败/翻转。试验仍不构成正式采用。</p>'
    table+='<table border="1" cellpadding="6"><tr><th>关节</th><th>失败采样</th><th>翻转总数</th><th>回归定位</th></tr>'+''.join(rows)+'</table>'
    table+=f'<p><a href="{digest}.json">完整关键姿态回归数据</a> · <a href="collar.html">此前修正</a></p>'
    overrides={(r['layer_id'],r['component_id']):r['poses'] for r in checked['rows']}
    (output/'keys.html').write_text(render(document,source.skeleton,overrides,fk=True).replace('<main>',table+'<main>'),encoding='utf-8')
    print('Key regression:',sum(t['selected'] for c in checked['comparisons'] for t in c['trials']),'keys improved')
