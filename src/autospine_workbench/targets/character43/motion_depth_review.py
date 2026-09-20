"""Time-addressed source depth evidence, never a claim of pixel occlusion QA."""
from html import escape


def render(report):
    rows = []
    overlap = report.get('target_overlap')
    summary = ''
    if overlap:
        summary = (f'<p>目标同帧 alpha 交集：{overlap["visible_pair_samples"]} 个配对采样；'
            f'其中跨平面 {overlap["ambiguous_visible_pair_samples"]} 个，顺序建议与原顺序不同 '
            f'{overlap["order_mismatch_pair_samples"]} 个，未测量 {overlap["unmeasured_pair_samples"]} 个。'
            '采用原图 UV、双线性 alpha 与 8/255 阈值；CPU 像素中心采样不等于 GPU 或连续时间验收。</p>')
    failures = []
    reasons = {'visible_depth_straddle': '有可见交集的手臂跨越躯干前后',
               'visible_unmapped_order_conflict': '换序会跨过其他可见附件，缺少归属依据',
               'depth_overlap_pixel_budget': '超出像素检查预算，保留原顺序',
               'depth_overlap_attachment_unsupported': '当前附件类型尚未支持重叠检查'}
    for failure in report.get('order', {}).get('failures', []):
        time = failure['time']
        explanation = ''
        sources = {'source_depth': '源动作深度', 'visible_setup_order': '可见交集，保留原顺序',
                   'preserved_setup_order': '保留原顺序（未测量此配对交集）'}
        for edge in (failure.get('conflict') or {}).get('edges', []):
            overlap = edge.get('overlap')
            sample = (f'；{overlap["time"]:.3f} 秒，{overlap["overlap_pixels"]} 个交集像素'
                      if overlap else '')
            explanation += (f'<li>{escape(edge["back"])} 在 {escape(edge["front"])} 后方：'
                            f'{escape(sources.get(edge["source"], edge["source"]))}{sample}</li>')
        if explanation:
            explanation = '<ul>' + explanation + '</ul>'
        elif failure.get('pair'):
            explanation = '<p>' + escape(' / '.join(failure['pair'])) + '</p>'
        failures.append(f'<tr><td>顺序约束</td><td>{escape(reasons.get(failure["reason_code"], failure["reason_code"]))}</td>'
                    f'<td><a href="player.html?time={time:.9f}">{time:.3f} 秒</a>{explanation}</td></tr>')
    for pair in report['pairs']:
        label = escape(pair['arm_slot']+' / '+pair['torso_slot'])
        for event in pair['events']:
            time = event['tick']/1_000_000
            rows.append(f'<tr><td>{label}</td><td>前景建议：{escape(event["to_front_slot"])}</td>'
                f'<td><a href="player.html?time={time:.9f}">定位 {time:.3f} 秒</a></td></tr>')
        # Consolidate consecutive ambiguous frames instead of flooding the UI.
        segments = []
        for sample in pair['samples']:
            if sample['ambiguous']:
                if not segments or segments[-1][-1]['source_frame_index']+1 != sample['source_frame_index']:
                    segments.append([])
                segments[-1].append(sample)
        for segment in segments:
            start, end = segment[0]['tick']/1e6, segment[-1]['tick']/1e6
            rows.append(f'<tr><td>{label}</td><td>手臂跨越躯干深度，不能整层决定前后</td>'
                f'<td><a href="player.html?time={start:.9f}">{start:.3f}–{end:.3f} 秒</a></td></tr>')
    body = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>动作遮挡检查</title>
<style>body{{font:16px system-ui;background:#101922;color:#e7edf4;margin:24px;line-height:1.6}}
main{{max-width:1100px;margin:auto}}a{{color:#7bd8ff}}table{{border-collapse:collapse;width:100%}}
td,th{{text-align:left;padding:12px;border-bottom:1px solid #425365}}</style>
<main><a href="/motions.html">← 动作中心</a><h1>手臂与躯干的深度候选</h1>
<p>使用源动作的明确深度轴 {escape(report['depth_axis'])}，正方向朝向相机。
按真实权重识别目标附件；混合部件与未分类附件保留原绘制顺序。</p>
<p>换序候选 {report.get('switch_candidates', 0)} 个。{'已生成动态顺序候选，尚未人工验收。' if report.get('selected') else '本次没有更改绘制顺序。'}
源骨骼深度不等于目标像素遮挡；跨前后平面的手臂可能需要分区。
无候选也不代表遮挡已通过。</p>
<p>采用 4% / 2% 源腿长的迟滞带，连续 3 帧形成换序建议，避免单帧抖动。</p>
{summary}
<table><thead><tr><th>附件配对</th><th>诊断</th><th>时间轴</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan="3">没有换序或跨平面记录；请结合映射覆盖与画面检查。</td></tr>'}</tbody></table>
<details><summary>未采用的采样约束（{len(failures)} 项）</summary><table>{''.join(failures)}</table></details>
<p><a href="depth-ownership.html">检查首个冲突位置的权重归属</a>（按需计算，不改变候选）</p>
<p><a href="motion-depth.json">完整来源与逐帧证据</a> · <a href="player.html">播放当前候选</a></p>
</main></html>'''
    return body.encode('utf-8')
