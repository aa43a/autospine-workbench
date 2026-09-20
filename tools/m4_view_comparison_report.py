"""Compare same-source target variants without hiding unsupported baseline cases."""
import argparse
from html import escape
import json
from pathlib import Path

from m4_motion_cohort import digest,save
from m4_motion_cohort_report import rows,label,summary


def compare(baseline,variants):
    sources={s['id']:s for s in baseline['motions']}
    output={s['id']+'/'+c['id']:[] for s in baseline['motions'] for c in baseline['characters']}
    counts={}
    for name,plan,state in variants:
        if name in counts: raise ValueError('comparison_variant_name_duplicate')
        if plan['characters']!=baseline['characters'] or plan.get('expected_profiles')!=baseline.get('expected_profiles'):
            raise ValueError('comparison_character_or_policy_mismatch')
        if digest(plan)!=digest(baseline) and plan.get('baseline_plan_sha256')!=digest(baseline):
            raise ValueError('comparison_baseline_mismatch')
        if len({s['id'] for s in plan['motions']})!=len(plan['motions']):
            raise ValueError('comparison_duplicate_motion')
        for source in plan['motions']:
            if source['id'] not in sources or source['sha256']!=sources[source['id']]['sha256']:
                raise ValueError('comparison_source_bytes_mismatch')
        records=rows(plan,state); counts[name]=summary(records)
        planned={s['id']:s for s in plan['motions']}
        by_cell={r['cell']:r for r in records}
        for cell in output:
            row=by_cell.get(cell)
            source=planned.get(cell.split('/')[0])
            output[cell].append(dict(variant=name,view=source['view'] if source else None,
                yaw=source.get('projection',{}).get('yaw_degrees') if source else None,
                result=row,status=row['status'] if row else 'not_planned'))
    return dict(baseline_plan_sha256=digest(baseline),cells=output,counts=counts,authority='none',
                scope='same_source_and_character_variant_comparison_not_visual_acceptance')


def render(report):
    lines=[]
    for cell,variants in report['cells'].items():
        cards=[]
        for variant in variants:
            row=variant['result']
            if row is None:
                cards.append('<td>本组未安排；正面基线仍保留</td>'); continue
            text=[variant['view']+(f" / {variant['yaw']}°" if variant['yaw'] is not None else ''),
                  label(row['status']), '几何：'+label(row['geometry']),
                  '接触：'+label(row['contact']), '遮挡：'+label(row['depth']),
                  '综合：'+label(row['readiness']), 'Runtime 帧：'+str(row['runtime_frames'] or '未完成')]
            links=''
            if row['status']=='succeeded':
                prefix='http://127.0.0.1:8918/api/motions/'+row['job_id']+'/view/'
                links='<p>'+ ' · '.join('<a href="'+escape(prefix+path)+'">'+caption+'</a>' for path,caption in
                    [('player.html','播放'),('contact.html','接触'),('depth.html','遮挡')])+'</p>'
            cards.append('<td>'+'<br>'.join(escape(t) for t in text)+links+'</td>')
        lines.append('<tr><th>'+escape(cell)+'</th>'+''.join(cards)+'</tr>')
    headers='<th>动作 / 角色</th>'+''.join('<th>'+escape(n)+'</th>' for n in report['counts'])
    return '''<!doctype html><meta charset="utf-8"><title>M4 同源视角对比</title>
<style>body{font:15px system-ui;background:#101923;color:#e7eff6;padding:24px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #456;padding:12px;vertical-align:top}a{color:#70daff}thead{position:sticky;top:0;background:#182735}</style>
<h1>M4 同源视角对比</h1><p>同一份源动作、同一角色版本与检查策略。此页为生成时快照，运行中和未检查均不计通过。
换视角通过不抹除原视角失败；捕获完成不代表画面可接受。未读取人工验收记录。</p>'''+ '<table><thead><tr>'+headers+'</tr></thead><tbody>'+''.join(lines)+'</tbody></table>'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline',type=Path); parser.add_argument('output',type=Path)
    parser.add_argument('--variant',nargs=3,action='append',required=True,metavar=('NAME','PLAN','STATE'))
    args=parser.parse_args()
    read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
    report=compare(read(args.baseline),[(n,read(p),read(s)) for n,p,s in args.variant])
    save(args.output.with_suffix('.json'),report)
    args.output.write_text(render(report),encoding='utf-8')
    print(json.dumps(report['counts'],ensure_ascii=False))


if __name__=='__main__':main()
