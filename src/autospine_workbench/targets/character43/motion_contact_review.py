"""Readable contact exceptions linked to the exact candidate's timeline."""
from html import escape

STATES = {'unavailable_no_labels': '源动作无接触标签，不能判断接触是否正确',
          'ankle_proxy_passed': '踝部支点采样通过', 'ankle_proxy_corrected': '已采用小幅根骨修正',
          'needs_changes': '支撑期存在滑移，需要调整'}
REASONS = {'motion_contact_correction_disabled': '本次关闭了自动修正',
           'motion_contact_correction_limit_or_conflict': '所需位移过大或双脚目标冲突',
           'motion_contact_transition_too_fast': '接触切换的修正速度过大',
           'motion_contact_residual_after_correction': '修正后密集采样仍有滑移'}


def render(report):
    rows = []
    for before, after in zip(report['before']['intervals'], report['after']['intervals']):
        time = after['worst_time']
        rows.append(f'<tr><td>{"左脚" if before["limb"] == "leg.left" else "右脚"}</td>'
            f'<td>{before["start"]:.3f}–{before["end"]:.3f} 秒</td>'
            f'<td>{before["max_drift_px"]:.3f} px</td><td>{after["max_drift_px"]:.3f} px</td>'
            f'<td>{"通过" if after["passed"] else "需调整"}</td>'
            f'<td><a href="player.html?time={time:.9f}" target="_blank" rel="noopener">定位 {time:.3f} 秒</a></td></tr>')
    reasons = ''.join('<li>'+escape(REASONS.get(r, r))+'</li>' for r in report['reason_codes'])
    correction = report.get('correction')
    detail = (f'<p>尝试修正峰值：{correction["max_correction_px"]:.3f} px；'
              f'双脚目标残差：{correction["max_residual_px"]:.3f} px。</p>') if correction else ''
    body = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>动作接触检查</title>
<style>body{{font:16px system-ui;background:#101922;color:#e7edf4;margin:24px;line-height:1.6}}
main{{max-width:1100px;margin:auto}}a{{color:#7bd8ff}}table{{border-collapse:collapse;width:100%}}
td,th{{text-align:left;padding:12px;border-bottom:1px solid #425365}}.scroll{{overflow-x:auto}}</style>
<main><a href="/motions.html">← 动作中心</a><h1>{escape(STATES[report['status']])}</h1>
<p>比较源动作标注的支撑期内，角色踝部支点相对于该段起点的位移。未测量鞋底、地面碰撞或遮挡。</p>
<p>阈值：{report['before']['drift_limit_px']:.3f} px（角色腿长的 1%）。区间终点不属于支撑期；同时检查终点前的姿态。</p>
<p>自动修正：{'已采用' if report['selected'] else '未采用'}。在动作中心取消“尝试小幅支撑修正”后重建，可保留未修正版。</p>
{detail}<ul>{reasons}</ul><div class="scroll"><table><thead><tr><th>支点</th><th>支撑区间</th>
<th>原动作最大滑移</th><th>当前候选最大滑移</th><th>采样结论</th><th>时间轴</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div><p><a href="motion-contact.json">完整检查数据</a> ·
<a href="player.html">播放当前候选</a></p><p>采样检查不等于连续时间或人工视觉验收。</p></main></html>'''
    return body.encode('utf-8')
