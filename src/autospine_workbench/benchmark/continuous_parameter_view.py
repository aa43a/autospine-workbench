"""Plot reference and fitted target parameters in fixed source-pair order."""
from html import escape


def render(report):
    cards=[]
    for relation in report['analysis']['relations']:
        for group in relation['groups']:
            title=f'{relation["driver"]} 弧段 {group["driver_arc"]} → {relation["follower"]} 弧段 {group["follower_arc"]}'
            body=f'<p>{escape(group["reason_code"])}；原对应数 {len(group["pairs"])}。</p>'
            if group['status']=='candidate_requires_review':
                before=group['reference_parameters'];after=[s['parameter'] for s in group['samples']];maximum=max(before+after)+.5
                plot=[]
                for values,color in ((before,'#d87725'),(after,'#167cca')):
                    points=' '.join(f'{30+i*520/(len(values)-1):.3f},{220-v*190/maximum:.3f}' for i,v in enumerate(values))
                    plot.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>')
                body+=f'<p>最大世界位移 {group["max_world_shift_px"]:.3f} px；参数平方改动 {group["cost"]:.3f}；方向 {group["direction"]}。</p><svg viewBox="0 0 580 250" role="img" aria-label="原始和连续参数曲线">{"".join(plot)}<text x="30" y="245">横轴：固定源序　纵轴：目标弧长参数</text></svg>'
            cards.append(f'<section><h2>{escape(title)}</h2>{body}</section>')
        if relation['blocked_pairs']:cards.append(f'<p>{escape(relation["driver"])}：{len(relation["blocked_pairs"])} 条原对应仍无法唯一分组。</p>')
    return '<!doctype html><meta charset="utf-8"><title>连续接缝参数</title><style>body{font:16px system-ui;background:#edf1f5;color:#20344b;margin:24px}section{background:white;padding:20px;margin:16px 0}svg{width:100%;max-width:650px;background:#fafafa}h2{font-size:20px}</style><h1>有界连续接缝参数</h1><p>橙色：原目标参数；蓝色：有界单调参数。曲线通过只表示参数可行，不表示动画裂缝已修复。原动画未变，尚未求解 deform 或采用结果。</p>'+(''.join(cards) or '<p>无接缝关系，不计为通过。</p>')
