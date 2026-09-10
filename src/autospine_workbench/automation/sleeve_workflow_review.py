"""Compact workflow result; cached computation never implies visual approval."""
from html import escape


def render(report):
    rows=[]
    for row in report['records']:
        label=escape(row['layer_id']+' / '+row['component_id'])
        if row.get('motion_profile')=='ordinary-forearm30-hand30-sine129-v1':label+=' · 普通袖四轨'
        action=f'<a href="{escape(row["download"],quote=True)}">下载 Spine 候选</a>' if row['download'] else '需继续处理'
        if row.get('runtime_report'):action+=f' · <a href="{escape(row["runtime_report"],quote=True)}">官方核心报告</a>（{escape(row["runtime_status"])}）'
        if row.get('software_contact'):
            c=row['software_contact'];action+=f'<p>软件接缝采样 {c["tested_samples"]}；空白失败 {c["failed_samples"]}；源图不可观测界面 {c["unobservable_interfaces"]}。此项为软件证据。</p>'
        if row.get('software_overlap'):
            o=row['software_overlap'];action+=f'<p>软件重叠检查 {o["frames"]} 帧；新增双覆盖 {o["affected_frames"]} 帧；单对峰值 {o["peak_excess_pair_pixels"]} 像素。仅诊断。</p>'
        else:action+='<p>软件重叠尚未检查；GPU未验证。</p>'
        if row.get('official_framebuffer'):
            f=row['official_framebuffer'];action+=f'<p>官方WebGL（SwiftShader）{f["frames"]}帧；袖口空白失败 {f["failed_samples"]}；新增双覆盖峰值组 {f["overlap_affected_peaks"]}/{f["overlap_peak_pairs"]}，最大 {f["overlap_peak_pixels"]} 像素。遮挡待复核。</p>'
        rows.append(f'<tr><td>{label}</td><td>{escape(row["status"])}</td><td>{escape(row["reason_code"])}</td><td>{action}</td></tr>')
    stages=' → '.join(escape(s['id'])+('（复用）' if s['cached'] else '✓') for s in report['steps'])
    project=escape(report['project_id'])
    ordinary=any(r.get('motion_profile')=='ordinary-forearm30-hand30-sine129-v1' for r in report['records'])
    ordinary_link=(f'<p><a href="spine/{project}/ordinary/index.html">普通袖四轨诊断时间轴</a></p>' if ordinary else '')
    completed={s['id'] for s in report['steps'] if s['status']=='succeeded'}
    timeline=next((name for name in ('repair','cuff','boundary') if name in completed),'boundary')
    runtime_note=('已导出区域官方核心数值验证通过；GPU与alpha接缝仍未验证。' if report['runtime_status']=='core_passed'
        else '官方核心未完成或未通过；GPU与alpha接缝仍未验证。')
    if report.get('framebuffer_review'):
        runtime_note='官方WebGL捕获已执行，逐袖结果见上表；未证明全域遮挡与完整角色通过。'
        runtime_note+=f'<a href="{escape(report["framebuffer_review"],quote=True)}">查看帧缓冲及重叠六视图</a>。'
    return f'''<!doctype html><meta charset="utf-8"><title>袖装重建 · {project}</title>
<style>body{{font:17px system-ui;background:#152332;color:#eef;margin:32px;max-width:1200px}}a{{color:#6dd8ff}}td,th{{padding:14px;text-align:left;border-bottom:1px solid #456}}table{{width:100%}}p{{line-height:1.8}}</style>
<h1>{project} · 袖装候选重建</h1><p>{stages}</p>
<p>普通袖采用前臂 ±30° / 手 ±30° 四轨；宽袖采用前臂 ±30° / 手 ±30° / 垂布 ±10° 七轨。已完成计算不等于通过质量检查。</p>
<table><thead><tr><th>区域</th><th>状态</th><th>原因</th><th>操作</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<p><a href="{timeline}/{project}/index.html">拖动时间轴查看通过/失败轨道</a></p>
{ordinary_link}
<p>{runtime_note}不得将可下载候选视为发布授权。相同输入再次运行会校验并复用已完成步骤。</p>'''
