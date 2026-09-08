"""Operator-facing included/missing inventory without inferred approvals."""
from html import escape


def render(report,names):
    labels={'binding_pending':'绑定待确认','selected_mesh_candidate_not_integrated':'已选Mesh尚未接入当前动画',
            'binding_exclude':'已排除','binding_requires_split':'需要切分','binding_semantic_review':'需要语义复核'}
    page='<!doctype html><meta charset="utf-8"><style>body{font:17px system-ui;margin:30px}th,td{padding:10px;border-bottom:1px solid #ddd}table{border-collapse:collapse}</style><h1>刚性绑定与四肢候选组合</h1><p>仅已选择刚性绑定 + 原四肢候选；尚未完成整角色动画或生产验收。</p><a href="preview.zip">下载 Spine 4.3.26 预览包</a>'
    page+='<p>已接入刚性图层：'+escape('、'.join(names[n] for n in report['rigid_layers']))+'</p>'
    if report.get('integrated_arms'):
        page+='<p>已接入手臂Mesh：'+escape('、'.join(names[n] for n in report['integrated_arms']))+'</p><a href="binding-review.html">集中复核剩余图层</a>'
    page+='<p>残余像素仍排除：'+str(report['residual_visible_pixels'])+'</p><h2>缺项清单</h2><table><tr><th>图层</th><th>原因</th></tr>'
    for row in report['excluded_layers']:
        page+='<tr><td>'+escape(names[row['layer_id']])+'</td><td>'+escape(labels.get(row['reason_code'],row['reason_code']))+'</td></tr>'
    return page+'</table><p>图层顺序沿用未复核源顺序；接缝及完整视觉验收仍需后续验证。</p>'
