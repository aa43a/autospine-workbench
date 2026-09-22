"""Build interval links from measured arm/torso depth evidence, without reordering."""
import argparse
from html import escape
import json
from pathlib import Path


def intervals(samples):
    rows=[]
    for s in samples:
        overlap=s['overlap']
        state=('unmeasured' if overlap['status']!='sampled' else 'no_overlap' if not overlap['overlap_pixels']
               else 'straddling' if s['ambiguous'] else 'measured')
        key=(state,s['current_front_slot'] if state=='measured' else None)
        t=s['tick']/1e6
        if rows and rows[-1]['key']==key:rows[-1].update(end=t,count=rows[-1]['count']+1)
        else:rows.append(dict(key=key,start=t,end=t,count=1))
    return rows


def render(root,player):
    summary=json.loads((root/'summary.json').read_bytes());sections=[];records=[]
    labels={'unmeasured':'未测量','no_overlap':'无可见重叠','straddling':'跨越躯干深度，不能整层排序','measured':'源深度给出整层前后建议'}
    for i,item in enumerate(summary['rows']):
        report=json.loads((root/(str(i)+'.json')).read_bytes());body=[]
        for pair in report['pairs']:
            for interval in intervals(pair['samples']):
                state,front=interval['key'];start=interval['start'];end=interval['end']
                link=f'{player}?character={i}&time={start}'
                description=labels[state]+(f'：前侧 {front}' if front else '')
                body.append(f'<tr><td>{escape(pair["arm_slot"])} / {escape(pair["torso_slot"])}</td><td>{start:.3f}–{end:.3f}s</td><td>{escape(description)}</td><td><a href="{escape(link,quote=True)}">同步定位</a></td></tr>')
                records.append(dict(character=item['character'],pair=[pair['arm_slot'],pair['torso_slot']],**interval))
        sections.append(f'<h2>{escape(item["character"])}</h2><table>{"".join(body)}</table>')
    html='<!doctype html><meta charset="utf-8"><title>Reach 深度异常定位</title><style>body{background:#14222e;color:#eef4fa;font:16px sans-serif;margin:32px}td{padding:10px;border-bottom:1px solid #456}a{color:#6dd5ff}</style><h1>Reach：同视角深度与重叠定位</h1><p>45° 源肢体视角；躯干与图像未整体侧转。只诊断，不改变绘制顺序。区间表示连续采样点分组，不证明点间连续安全。</p><p>跨面样本需要局部深度或分区证据；源前后建议不等于最终遮挡验收，裙腿与头发不在本检查范围内。</p>'+''.join(sections)
    (root/'index.html').write_text(html,encoding='utf-8')
    (root/'intervals.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('player')
    a=p.parse_args();render(a.root,a.player)
