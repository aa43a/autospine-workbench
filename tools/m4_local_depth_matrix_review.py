"""Render all planned cells, including pending and incomplete diagnostic coverage."""
import argparse
import html
import json
from pathlib import Path
from m4_motion_cohort import digest

LABELS={'uniform_back_proxy':'模型后侧','uniform_front_proxy':'模型前侧','no_visible_overlap':'无可见重叠',
        'depth_margin_ambiguity':'深度接近','missing_depth_support':'深度不足','mixed_front_back_support':'前后混合'}


def render(plan,state):
    if state['identity']['plan_sha256']!=digest(plan):raise ValueError('matrix_review_plan_identity')
    rows=[]
    for motion in plan['motions']:
        for character in plan['characters']:
            key=motion['id']+'/'+character['id'];cell=state['cells'].get(key)
            title=html.escape(key)
            if cell is None:
                rows.append(f'<tr><td>{title}</td><td>尚未检查</td><td>—</td></tr>');continue
            counts={}
            for pair in cell['causes']['pairs']:
                for reason,value in pair['reasons'].items():counts[reason]=counts.get(reason,0)+value
            text='；'.join(f'{LABELS.get(k,"未测："+k[11:] if k.startswith("unmeasured:") else k)} {v}' for k,v in counts.items())
            link='http://127.0.0.1:8918/motions.html#'+cell['job_id']
            rows.append(f'<tr><td>{title}</td><td>{html.escape(text)}</td><td><a href="{html.escape(link,quote=True)}">候选与补充检查</a></td></tr>')
    return ('<!doctype html><meta charset="utf-8"><title>M4 固定矩阵局部深度检查</title>'
        '<style>body{background:#182531;color:#eee;font:16px sans-serif;max-width:1300px;margin:24px auto}table{border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #54616d;text-align:left}a{color:#8dd8ff}</style>'
        f'<h1>M4 三角色 × 八类动作</h1><p>局部深度补充检查：{len(state["cells"])}/{len(plan["motions"])*len(plan["characters"])} 个候选。'
        '保留全部计划项、原候选和未测记录。这些是模型检查数，不是错误率；本次不重做 Runtime 捕获，也不自动验收。</p>'
        '<p>工作台入口：在此查看遮挡状态 → 查看局部深度补充检查。</p><table><tr><th>动作 / 角色</th><th>检查结果</th><th>入口</th></tr>'+''.join(rows)+'</table>')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('plan',type=Path);parser.add_argument('folder',type=Path)
    args=parser.parse_args();state=json.loads((args.folder/'state.json').read_bytes())
    (args.folder/'index.html').write_text(render(json.loads(args.plan.read_bytes()),state),encoding='utf-8')
