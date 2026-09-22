"""Compact exact-candidate local depth comparison with timed player links."""
import argparse
from html import escape
import json
from pathlib import Path


def render(base,enhanced,player,output):
    first=json.loads((base/'summary.json').read_bytes())['rows']
    second=json.loads((enhanced/'summary.json').read_bytes())['rows']
    if len(first)!=len(second):raise ValueError('local_depth_comparison_inventory')
    sections=[];evidence=[]
    for i,(a,b) in enumerate(zip(first,second)):
        if (a['candidate'],a['samples'])!=(b['candidate'],b['samples']):
            raise ValueError('local_depth_comparison_identity')
        details=json.loads((enhanced/(str(i)+'.json')).read_bytes())
        pending=[r for r in details['records'] if r['status'] not in ('uniform_front_proxy','uniform_back_proxy','no_overlap')]
        links=[]
        # Every unresolved source sample is reachable; same time may have multiple pairs.
        for r in pending:
            t=r['time'];url=f'{player}?character={i}&time={t}'
            links.append(f'<tr><td><a href="{escape(url,quote=True)}">{t:.3f}s</a></td><td>{escape(" / ".join(r["pair"]))}</td><td>{escape(str(r.get("counts",r.get("reason"))))}</td></tr>')
        table='<table><tr><th>模型</th><th>前</th><th>后</th><th>歧义</th><th>缺失</th></tr>'
        for label,row in [('基础骨段',a),('躯干平面＋手部观测',b)]:
            table+=f'<tr><td>{label}</td>'+''.join(f'<td>{row["pixels"][key]}</td>' for key in ('front','back','ambiguous','unknown'))+'</tr>'
        sections.append(f'<h2>{escape(b["character"])}</h2>{table}</table><p>检查 {b["samples"]} 个部件对采样；仍待解释 {len(pending)} 个。</p><details><summary>展开异常时间，点击同步定位</summary><table>{"".join(links)}</table></details>')
        evidence.append(dict(character=b['character'],candidate=b['candidate'],baseline=a,enhanced=b,
                             pending_times=sorted({r['time'] for r in pending})))
    text='<!doctype html><meta charset="utf-8"><title>Reach 局部深度对照</title><style>body{font:16px sans-serif;background:#14222e;color:#eee;margin:32px}td,th{padding:10px;border-bottom:1px solid #456}a{color:#6dd5ff}summary{cursor:pointer}</style><h1>Reach：局部深度解释与剩余异常</h1><p>只诊断，不修改绘制顺序或采用候选。数字是跨帧、跨部件对的像素计数之和，不是独立像素数或视觉错误数。</p><p>增强模型假设躯干平面、骨段截面及权重深度区间；它不是实测皮肤或袖布表面。这里只检查源帧，尚未验证帧间排序。</p>'+''.join(sections)
    output.write_text(text,encoding='utf-8')
    output.with_suffix('.json').write_text(json.dumps(dict(authority='none',selected=False,rows=evidence,
        enhanced_assumptions=['planar_torso','observed_hand_endpoints','weighted_depth_intervals'],
        scope='source_sample_proxy_comparison_not_order_or_visual_acceptance'),ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('base',type=Path);p.add_argument('enhanced',type=Path)
    p.add_argument('player');p.add_argument('output',type=Path)
    a=p.parse_args();render(a.base,a.enhanced,a.player,a.output)
