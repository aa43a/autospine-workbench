"""Export area-aware material and bone-group exception localization."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
from autospine_workbench.targets.character43.deform_addition import entries
from autospine_workbench.targets.character43.surface_exception_regions import summarize


def run(surface_path,poses_path,output):
    raw=surface_path.read_bytes();surfaces=json.loads(raw);pose_raw=poses_path.read_bytes();poses=json.loads(pose_raw)
    if sha256(raw).hexdigest()!=poses['surface_sha256']:raise ValueError('exception_surface_identity')
    records=[]
    for p in poses['records']:
        s=surfaces['surfaces'][p['slot']]
        report=summarize(s['vertices'],s['triangles'],s['material_roles'],p['dq_evidence'],
                         entries({'vertices':s['source_weighted_vertices']}),[b['name'] for b in s['source_bones']])
        records.append(dict(slot=p['slot'],time=p['time'],report=report))
    output.mkdir(parents=True,exist_ok=False)
    result=dict(surface_sha256=sha256(raw).hexdigest(),poses_sha256=sha256(pose_raw).hexdigest(),
                records=records,accepted=False)
    (output/'exceptions.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    panels=[]
    for row in records:
        body=''.join('<tr><td>'+escape(r['material_role'])+'</td><td>'+escape(', '.join(r['bones']))+
            f'</td><td>{len(r["triangles"])}</td><td>{r["rest_area"]:.3f}</td><td>{100*r["fraction_of_role_area"]:.3f}%</td>'+
            '<td><details><summary>三角形与范围</summary>'+escape(json.dumps(dict(triangles=r['triangles'],bounds=r['bounds'])))+
            '</details></td></tr>' for r in row['report']['regions'])
        panels.append(f'<section><h2>{escape(row["slot"])} · {row["time"]:.6f}s</h2><table><tr>'
            '<th>表面</th><th>关联骨骼</th><th>面数</th><th>失败面积 px²</th><th>占该类表面</th><th>定位</th></tr>'+body+'</table></section>')
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>表面异常定位</title>'
        '<style>body{background:#18232e;color:#eee;font:16px sans-serif;margin:24px}table{border-collapse:collapse;width:100%}'
        'td,th{border:1px solid #456;padding:8px}details{max-width:400px;overflow-wrap:anywhere}</style>'
        '<h1>表面异常 · 按原面积与连通区域定位</h1><p>小面积不等于可接受。骨骼关联不代表因果，未判定遮挡可见性。</p>'+''.join(panels),encoding='utf-8')
    print(json.dumps(dict(samples=len(records),regions=sum(len(r['report']['regions']) for r in records))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('surface','poses','output'):p.add_argument(key,type=Path)
    a=p.parse_args();run(a.surface,a.poses,a.output)
