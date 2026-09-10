"""Compact workflow result; cached computation never implies visual approval."""
from html import escape


def render(report):
    rows=[]
    for row in report['records']:
        label=escape(row['layer_id']+' / '+row['component_id'])
        action=f'<a href="{escape(row["download"],quote=True)}">下载 Spine 候选</a>' if row['download'] else '需继续处理'
        rows.append(f'<tr><td>{label}</td><td>{escape(row["status"])}</td><td>{escape(row["reason_code"])}</td><td>{action}</td></tr>')
    stages=' → '.join(escape(s['id'])+('（复用）' if s['cached'] else '✓') for s in report['steps'])
    project=escape(report['project_id'])
    return f'''<!doctype html><meta charset="utf-8"><title>袖装重建 · {project}</title>
<style>body{{font:17px system-ui;background:#152332;color:#eef;margin:32px;max-width:1200px}}a{{color:#6dd8ff}}td,th{{padding:14px;text-align:left;border-bottom:1px solid #456}}table{{width:100%}}p{{line-height:1.8}}</style>
<h1>{project} · 袖装候选重建</h1><p>{stages}</p>
<p>动作范围：前臂 ±30° / 手 ±30° / 垂布 ±10°，含组合测试。候选生成已完成，正式采用仍需复核。</p>
<table><thead><tr><th>区域</th><th>状态</th><th>原因</th><th>操作</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<p><a href="boundary/{project}/index.html">拖动时间轴查看通过/失败轨道</a></p>
<p>此工作流未执行 GPU 与 alpha 接缝验证；不得将可下载候选视为发布授权。相同输入再次运行会校验并复用已完成步骤。</p>'''
