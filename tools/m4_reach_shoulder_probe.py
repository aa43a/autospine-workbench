"""Inspect and solve source-supported shoulder boundaries on isolated reach views."""
import argparse
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import sample,matrices
from autospine_workbench.targets.character43.shoulder_source import contexts
from autospine_workbench.targets.character43.shoulder_boundary import prepare,solve
from autospine_workbench.targets.character43.skirt_candidate import inverse


def run(comparison,output,time):
    if not math.isfinite(time) or time<0:raise ValueError('reach_shoulder_time_invalid')
    inventory=json.loads((comparison/'comparison.json').read_bytes());rows=[]
    for index,item in enumerate(inventory['rows']):
        folder=comparison/str(index)/'yaw-45'
        receipt=json.loads((folder/'pose/report.json').read_bytes())
        mesh=json.loads((folder/'mesh/report.json').read_bytes())
        files=AnimatedStore(folder/'mesh/isolated-store').read(mesh['candidate_bundle_sha256'])
        source=AnimatedStore('workspace').read(receipt['character_sha256'])
        doc=json.loads(files['skeleton.json']);base=json.loads(source['skeleton.json'])
        duration=max(k['time'] for tracks in doc['animations']['external-motion']['bones'].values() for keys in tracks.values() for k in keys)
        if time>duration:raise ValueError('reach_shoulder_time_outside_motion')
        if {k:v for k,v in doc.items() if k!='animations'}!={k:v for k,v in base.items() if k!='animations'}:
            raise ValueError('reach_shoulder_setup_changed')
        source['skeleton.json']=files['skeleton.json']
        document,parts=contexts(source);name='external-motion'
        rest=matrices(dict(document,animations={'setup':{}}),'setup',0)
        current=matrices(document,name,time);worlds=sample(document,name,time)[0]
        for part in parts:
            row=dict(job=item['job'],candidate=mesh['candidate_bundle_sha256'],source_character=receipt['character_sha256'],
                slot=part['slot'],time=time,source_contact_pixels=len(part['contact']))
            try:context=prepare(part['points'],part['triangles'],part['contact'],part['root'],part['distal'])
            except ValueError as e:
                rows.append(dict(row,status='unsupported_contact',reason=str(e)));continue
            def gap(points):
                a,b,c,d,x,y=current['chest'];values=[]
                for v in context['pins']:
                    u,w=inverse(rest['chest'],part['points'][v]);values.append(math.dist(points[v],[a*u+b*w+x,c*u+d*w+y]))
                return max(values)
            world=worlds[part['slot']]
            corrected,evidence=solve(document,name,time,part['points'],part['triangles'],world,context)
            movable=set(context['pins']+context['free'])
            fixed=max((math.dist(a,b) for i,(a,b) in enumerate(zip(world,corrected)) if i not in movable),default=0)
            q=evidence['geometry']
            rows.append(dict(row,status='single_pose_candidate',context=context,before_pin_gap=gap(world),
                after_pin_gap=gap(corrected),evidence=evidence,fixed_error=fixed,
                passed=not q['bad_triangles'] and q['max_edge_stretch']<=2 and evidence['within_budget'] and fixed<=1e-7))
            print(json.dumps({k:v for k,v in rows[-1].items() if k not in ('context','evidence')}),flush=True)
    payload=dict(profile='reach-source-shoulder-boundary-probe-v1',authority='none',selected=False,
        scope='single_pose_geometric_boundary_not_alpha_raster_or_full_motion',rows=rows)
    with output.open('x',encoding='utf-8') as f:json.dump(payload,f,indent=2)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('comparison',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--time',type=float,default=2.4);a=p.parse_args();run(a.comparison,a.output,a.time)
