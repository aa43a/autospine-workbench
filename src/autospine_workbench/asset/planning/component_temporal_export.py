"""Immutable temporal diagnostics summarized beside the timeline."""
from html import escape
from .component_temporal_qa import build, passed
from ...resolved_project import canonical_sha256
from ...benchmark.mesh_storage import publish_mesh_report,read_mesh_report,export_mesh


def export(state,output,document,correction,source):
    result=build(document,correction,source.skeleton)
    source.assert_current()
    digest=publish_mesh_report(state,'project-component-partitions',result)
    checked=read_mesh_report(state,'project-component-partitions',digest)
    if canonical_sha256(checked)!=canonical_sha256(build(document,correction,source.skeleton)):
        raise ValueError('component_temporal_replay_mismatch')
    source.assert_current(); export_mesh(output/f'{digest}.json',checked)
    rows=[]
    for row in checked['rows']:
        before=sum(not passed(t['before']) for t in row['ticks']);after=sum(not passed(t['after']) for t in row['ticks'])
        rows.append(f'<tr><td>{escape(row["layer_id"])} / {escape(row["component_id"])} / {escape(row["bone_id"])}</td><td>{before} → {after}</td>'
                    f'<td>{row["new_failure_count"]}</td><td>{escape(str(row["interior_failure_times"]))}</td></tr>')
    return (f'<h2>播放插值采样检查</h2><p>每轨道 33 个时间点，每 0.25 秒检查。端点通过不保证中间通过；这不是连续时间证明或官方 Runtime。</p>'
            '<table border="1" cellpadding="6"><tr><th>区域／关节</th><th>失败采样 原→修正</th><th>新增失败</th><th>端点通过但内部失败的秒数</th></tr>'
            +''.join(rows)+f'</table><p><a href="{digest}.json">播放插值报告（含关键点速度变化）</a></p>')
