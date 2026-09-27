"""Explain moving-source versus stationary-ankle checks without changing gates."""
import json
import math

from ...resolved_project import canonical_sha256
from ..spine43.continuous_pose import interpolate


def render(files):
    if 'motion-moving-ankles.json' not in files:
        return ''
    moving = json.loads(files['motion-moving-ankles.json'])
    contact = json.loads(files['motion-contact.json'])
    final = moving.get('final_check', {})
    identity = canonical_sha256(json.loads(files['skeleton.json']))
    if (not moving.get('applied') or final.get('skeleton_sha256') != identity
            or contact.get('final_timeline_check', {}).get('skeleton_sha256') != identity):
        return '<section><h2>来源脚端跟随</h2><p>当前骨架缺少匹配的最终检查，不能比较来源位移。</p></section>'
    trajectory = moving['trajectory']
    rows = []
    for interval in contact['after']['intervals']:
        side = {'leg.left': 0, 'leg.right': 1}[interval['limb']]
        frames = [dict(time=r['time'], vertices=r['targets'][side]) for r in trajectory]
        samples = interval['samples']
        if not samples:
            continue
        anchor = interpolate(frames, interval['start'], 'vertices')
        measured = [(s['time'], math.dist(interpolate(frames, s['time'], 'vertices'), anchor),
                     math.dist(interpolate(frames, s['time'], 'vertices'), [s['x'], s['y']]))
                    for s in samples]
        worst = max(measured, key=lambda r: r[2])
        source_drift = max(r[1] for r in measured)
        rows.append(f'<tr><td>{"左脚" if side == 0 else "右脚"}</td>'
                    f'<td>{interval["start"]:.3f}–{interval["end"]:.3f} 秒</td>'
                    f'<td>{source_drift:.3f} px</td>'
                    f'<td>{interval["max_drift_px"]:.3f} px</td>'
                    f'<td>{worst[2]:.6f} px</td>'
                    f'<td><a href="player.html?time={worst[0]:.9f}">{worst[0]:.3f} 秒</a></td></tr>')
    return ('<section><h2>来源脚端跟随与静止支撑</h2>'
            '<p>下表在同一接触采样时刻比较：来源轨迹已按角色腿长缩放，'
            '位移相对于本段起点；跟随误差比较同一时刻的来源目标与角色踝点。'
            '来源本身移动时，准确跟随仍可能超过静止支撑阈值。'
            '这不证明鞋底接地，也不会清除接触异常或自动接受候选。</p>'
            '<div class="scroll"><table><thead><tr><th>支点</th><th>区间</th>'
            '<th>来源最大位移</th><th>角色最大位移</th><th>最大跟随误差</th>'
            '<th>误差定位</th></tr></thead><tbody>'+''.join(rows)+
            '</tbody></table></div></section>')
