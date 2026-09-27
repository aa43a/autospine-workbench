"""Readable comparison for audited batch captures, preserving failed geometry."""
import argparse
from html import escape
import json
from pathlib import Path
from m4_transverse_batch_audit import audit


def run(state_root, probe, root):
    coverage = audit(state_root, probe, root)
    manifest = json.loads((root/'report.json').read_bytes())
    slot = json.loads((probe/'report.json').read_bytes())['slot']
    rows = []
    for index, record in enumerate(manifest['rows']):
        folder = record['folder']; evidence = json.loads((root/folder/'geometry.json').read_bytes())
        before, after = [next(r for r in evidence[key]['records'] if r['slot'] == slot)
                         for key in ('parent_geometry', 'geometry')]
        points = record['times'][1:] if index else record['times']
        links = f'<a href="{folder}/geometry.json">几何对照</a>'
        if 'runtime' in record:links += f' · <a href="{folder}/runtime/index.html">实际捕获画面</a>'
        rows.append(f'<tr><td>{index+1}</td><td>{points[0]:.6f}–{points[-1]:.6f} 秒</td>'
            f'<td>{len(points)}</td><td>{before["min_area_ratio"]:.6f} → {after["min_area_ratio"]:.6f}</td>'
            f'<td>{before["max_edge_stretch"]:.6f} → {after["max_edge_stretch"]:.6f}</td>'
            f'<td>{"通过" if record["geometry_passed"] else "存在异常"}</td><td>{links}</td></tr>')
    normalization = manifest['normalization']
    runtime = '全部声明时间点已通过数值一致性检查' if coverage['runtime_status']=='passed' else '尚未执行'
    html = f'''<!doctype html><html lang="zh"><meta charset="utf-8"><title>腿部修正分批验证</title>
<style>body{{background:#101922;color:#e7edf4;font:16px system-ui;margin:32px;line-height:1.6}}
a{{color:#81d5ff}}table{{border-collapse:collapse;width:100%}}td,th{{padding:12px;border:1px solid #435365;text-align:left}}
.notice{{padding:20px;background:#392b20;border-left:4px solid #efba74}}small{{overflow-wrap:anywhere}}</style>
<h1>腿部修正 · 完整动作分批对照</h1>
<p class="notice">实验结果未采用。Runtime 数值一致不代表变形自然；接触、遮挡和视觉验收仍待完成。
整角色几何：{'通过当前采样检查' if coverage['geometry_passed'] else '存在异常，保留失败结果'}。</p>
<p>已核实 {coverage['frames']} 个独立时间点，共 {coverage['batches']} 批。
官方 Runtime：{runtime}。所有原检查时间点均保留；批次中的重复起点不重复计数。</p>
<p>变形关键帧整理：{normalization.get('input_keys',0)} → {normalization.get('output_keys',0)}；
局部坐标曲线最大转换误差 {normalization['maximum_local_error']:.3g}。
该误差不是世界坐标误差或视觉质量评分。</p>
<h2>所选腿部 {escape(slot)} · 父候选 → 修正候选</h2>
<p>面积比例下限为 0.5；边长拉伸上限为 2。下列数值针对所选腿部，整角色列同时包含其他附件。
每批保留 setup 起点用于检查，时间范围仅展示该批新增时刻。</p>
<table><tr><th>批次</th><th>时间范围</th><th>独立帧</th><th>最小面积比例</th><th>最大边长拉伸</th><th>整角色几何</th><th>证据</th></tr>
{''.join(rows)}</table><p><a href="report.json">完整结果与来源记录</a></p>
<small>候选骨架：{escape(manifest['skeleton_sha256'])}<br>父候选：{escape(manifest['parent_artifact_sha256'])}</small></html>'''
    (root/'index.html').write_text(html, encoding='utf-8')
    return coverage


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('state_root','probe','output'):parser.add_argument(name, type=Path)
    args = parser.parse_args(); print(json.dumps(run(args.state_root,args.probe,args.output)))
