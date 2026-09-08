"""Local arc overlays and ordered-correspondence review without adoption controls."""
import base64
from html import escape


def render(report,curves,files):
    records={r['attachment']:r for r in curves['curves']['attachments']};sections=[]
    for relation in report['analysis']['relations']:
        figures=[]
        for side in ('driver','follower'):
            name=relation[side];r=records[name];w,h=r['size'];paths=[]
            for ai,arc in enumerate(report['analysis']['arcs'][name]):
                if arc['status']!='local_arc_candidate':continue
                curve=r['curves'][arc['curve']];edges=arc['edges']
                points=[curve['points'][e] for e in edges]+[curve['points'][edges[-1]+1]]
                coords=' '.join(f'{x},{y}' for x,y in points);x,y=points[0]
                paths.append(f'<polyline points="{coords}" fill="none" stroke="#ff335b" stroke-width="1.5"/><text x="{x+3}" y="{y}" fill="#102e65" font-size="8">{ai}</text>')
            raw=base64.b64encode(files['editor/images/'+name+'.png']).decode()
            figures.append(f'<figure><figcaption>{escape(name)}</figcaption><svg viewBox="0 0 {w} {h}" role="img" aria-label="局部支持弧段"><image href="data:image/png;base64,{raw}" width="{w}" height="{h}"/>{"".join(paths)}</svg></figure>')
        rows=[]
        for group in relation['groups']:
            rows.append('<tr>'+''.join(f'<td>{escape(str(v))}</td>' for v in
                (f'{group["driver_arc"]} → {group["follower_arc"]}',len(group['pairs']),group.get('direction','—'),
                 group.get('many_to_one_steps','—'),group.get('alternative_margin','—'),group['reason_code']))+'</tr>')
        sections.append(f'<section><h2>{escape(relation["driver"])} ↔ {escape(relation["follower"])}</h2><div class="figures">{"".join(figures)}</div>'
                        f'<p>原对应 {relation["source_pair_count"]}；无法唯一分组 {len(relation["blocked_pairs"])}。</p>'
                        '<table><tr><th>弧段</th><th>对应数</th><th>方向</th><th>多对一步数</th><th>次优代价差</th><th>状态</th></tr>'+''.join(rows)+'</table></section>')
    return '<!doctype html><meta charset="utf-8"><title>局部弧段与有序配对</title><style>body{font:16px system-ui;background:#edf1f5;color:#20344b;margin:24px}section{background:white;margin:16px 0;padding:20px}.figures{display:flex}figure{width:45%;margin:12px}svg{width:100%;height:480px;background:#ddd}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd5df;padding:8px;text-align:left}</style><h1>局部弧段与有序配对</h1><p>红线为原样本支持的局部弧段，编号仅用于诊断。间隔上限为 4 条纹理边；多解、非单调和多对一均保留复核。尚未运行形状求解或改变动画。</p>'+(''.join(sections) or '<p>无接缝对应，不计为通过。</p>')
