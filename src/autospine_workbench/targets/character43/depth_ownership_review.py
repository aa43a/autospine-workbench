"""On-demand, bounded diagnostic for an exact candidate's first order conflict."""
from hashlib import sha256
from html import escape
from copy import deepcopy
import json

from .depth_overlap_ownership import inspect
from .motion_depth_overlap import Probe


def build(files):
    depth = json.loads(files['motion-depth.json'])
    document = json.loads(files['skeleton.json'])
    report = dict(profile='first-order-conflict-ownership-v1', authority='none', selected=False,
                  skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
                  depth_sha256=sha256(files['motion-depth.json']).hexdigest(), samples=[],
                  scope='first_conflict_only_not_full_motion_validation')
    conflict = next((f for f in depth.get('order', {}).get('failures', [])
                     if f.get('conflict')), None)
    # Older immutable reports have failure times but no cycle witness. Recompute
    # only that source frame and its next midpoint, without publishing a candidate.
    if conflict is None:
        failure = next((f for f in depth.get('order', {}).get('failures', [])
                        if f.get('reason_code') == 'visible_unmapped_order_conflict'), None)
        if failure is not None:
            from .motion_depth_order import build as order
            subset = deepcopy(depth)
            ticks = sorted({s['tick'] for p in depth['pairs'] for s in p['samples']
                            if s['tick']/1e6 >= failure['time']})[:2]
            for pair in subset['pairs']:
                pair['samples'] = [s for s in pair['samples'] if s['tick'] in ticks]
            _, diagnosis = order(document, 'external-motion', subset,
                                 Probe(document, files, 'external-motion', pixel_budget=8_000_000))
            conflict = next((f for f in diagnosis['failures'] if f.get('conflict')), None)
            report['witness_recomputed'] = True
            report['witness_scope'] = 'first_failure_and_next_source_frame_with_midpoint'
    if conflict is None:
        report['status'] = 'conflict_witness_unavailable'
        return report
    probe = Probe(document, files, 'external-motion', pixel_budget=8_000_000)
    for edge in conflict['conflict']['edges'][:8]:
        if edge['source'] != 'visible_setup_order':
            continue
        time = edge['overlap']['time']
        try:
            result = inspect(probe, edge['back'], edge['front'], time)
        except ValueError as exc:
            result = dict(time=time, pair=[edge['back'], edge['front']],
                          status='unmeasured', reason_code=str(exc))
        report['samples'].append(result)
    report['status'] = 'diagnostic_only' if report['samples'] else 'no_visible_setup_edge'
    report['pixel_budget_used'] = 8_000_000-probe.remaining
    return report


def render(report):
    rows = []
    labels = {'chest': '胸部', 'arm.left': '左臂', 'arm.right': '右臂',
              'mixed': '人体与其他骨骼混合', 'unmapped': '没有源深度映射的骨骼'}
    for sample in report['samples']:
        time = sample['time']
        rows.append(f'<h2>{escape(" / ".join(sample["pair"]))}</h2>'
                    f'<a href="player.html?time={time:.9f}">定位 {time:.3f} 秒</a>')
        if sample.get('status') == 'unmeasured':
            rows.append('<p>未测量：'+escape(sample['reason_code'])+'</p>')
        for slot, result in sample.get('slots', {}).items():
            rows.append('<h3>'+escape(slot)+'</h3><ul>')
            for group in result['groups']:
                rows.append(f'<li>{escape(labels[group["group"]])}：{group["overlap_pixels"]} 个重叠像素。'
                            f'该类三角形使用的骨骼：{escape(", ".join(group["bones"]))}</li>')
            rows.append('</ul><p>'+('缺少布料三维深度依据，不能整体套用胸部深度。'
                         if result['missing_depth_evidence'] else
                         '权重属于已识别人体骨骼；仍需检查源深度跨度，不能仅凭归属采用换序。')+'</p>')
    return ('''<!doctype html><meta charset="utf-8"><title>遮挡区域归属</title>
<style>body{background:#101922;color:#e7edf4;font:16px system-ui;line-height:1.7;margin:32px;max-width:1100px}a{color:#7bd8ff}</style>
<a href="depth.html">← 遮挡检查</a><h1>冲突位置的实际权重归属</h1>
<p>仅检查首个冲突的可见原顺序边，最多八条。使用独立计算预算，不改变候选或自动采用结果。
按三角形全部正权重分类；混合区域与辅助骨不冒充胸部深度。共享边和折叠处各类计数可能重叠。</p>'''
            + ''.join(rows) + ('<p>此历史产物没有详细冲突证据，请重新构建候选。</p>' if not rows else '')
            + '<p><a href="depth-ownership.json">完整诊断记录</a></p>').encode('utf-8')
