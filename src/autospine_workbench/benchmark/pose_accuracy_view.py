"""Small read-only metrics page; missing references never look like zero error."""
from html import escape


def _value(number, *, ratio=False):
    if number is None:
        return '未评估'
    return f'{number * 100:.3f}%' if ratio else f'{number:.3f}'


def render_pose_accuracy(document):
    report = document['analysis']
    summary = report['summary']
    methods = {'baseline': '旧 bbox 基线', 'pose': '原始 Pose 坐标', 'optimized': '优化候选'}
    rows = []
    for key, label in methods.items():
        value = summary[key]
        rows.append(f'<tr><th>{label}</th><td>{value["available"]}/12</td><td>{value["compared"]}</td>'
                    f'<td>{_value(value["median_distance_px"])}</td>'
                    f'<td>{_value(value["core"]["median_distance_height_ratio"], ratio=True)}</td></tr>')
    comparisons = []
    for key, label in (('baseline_vs_pose', 'Pose 相对旧基线'), ('pose_vs_optimized', '优化相对 Pose')):
        value = summary['comparisons'][key]
        comparisons.append(f'<p>{label}：共同参考点 {value["compared"]}；'
                           f'逐点误差改变量中位数 {_value(value["median_delta_px"])} px。</p>')
    detail = []
    statuses = {'observed': '已标注', 'unmarked': '未标注', 'unobservable': '不可观测'}
    for row in report['records']:
        values = ''.join(f'<td>{_value(row["methods"][method]["distance_px"])}</td>' for method in methods)
        detail.append(f'<tr><th>{escape(row["joint_id"])}</th><td>{statuses[row["reference_status"]]}</td>{values}</tr>')
    reference = '已使用显式记录的 Benchmark 参考；部分标注不代表完整验收。' if report['reference_sha256'] else \
                '没有正式 Benchmark 参考，所有误差均未评估。请先独立标注，不要复制模型预测当作真值。'
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'">
<title>R2-B 姿态精度评估</title><style>
body{{font:16px/1.6 system-ui;max-width:1100px;margin:30px auto;padding:0 20px;color:#203047;background:#f5f7f9}}
.notice{{background:#fff1ce;padding:16px}}table{{border-collapse:collapse;width:100%;background:white}}
td,th{{border:1px solid #ccd5df;padding:10px;text-align:left}}.table{{overflow:auto}}
</style><h1>R2-B 姿态精度评估</h1><p class="notice">{reference}<br>
本页只有测量结果，不判定自动采用或生产合格。不可观测点不参与误差统计。</p>
<p>角色高度来自合成图 alpha：{_value(report['character_height_px'])} px。
核心关节为双侧肩、髋、踝；归一化误差使用角色高度，未使用画布高度。</p>
<div class="table"><table><tr><th>方法</th><th>可用点</th><th>已比较点</th><th>中位误差 px</th><th>核心中位误差 / 身高</th></tr>
{''.join(rows)}</table></div><h2>共同参考点对照</h2>
<p>改变量 = 后一种方法误差 − 前一种方法误差；负数表示误差减小。只比较共同有值的同一组参考点。</p>
{''.join(comparisons)}<h2>逐关节误差 px</h2><div class="table"><table>
<tr><th>关节</th><th>参考状态</th><th>旧基线</th><th>Pose</th><th>优化</th></tr>{''.join(detail)}</table></div></html>'''
