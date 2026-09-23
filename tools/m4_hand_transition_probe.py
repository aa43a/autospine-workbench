"""One fixed-budget mixed-vertex solve at existing hand-candidate key poses."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample,matrices
from autospine_workbench.targets.character43.deform_addition import entries,local_delta
from autospine_workbench.targets.character43.local_area_constraints import refine
from autospine_workbench.targets.character43.numeric_reference import read
from autospine_workbench.targets.spine43.continuous_pose import area
from m4_squat_stage_players import stage


def solve(files,slot):
    doc=json.loads(files['skeleton.json']);name='external-motion'
    if doc['animations'][name].get('attachments',{}).get('default',{}).get(slot,{}).get(slot,{}).get('deform'):
        raise ValueError('hand_transition_existing_deform_requires_explicit_rebase')
    setup=json.loads(files['rig-setup-reference.json'])['vertices'][slot]
    mesh=doc['skins'][0]['attachments'][slot][slot];owners=entries(mesh)
    triangles=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]
    edges=sorted({tuple(sorted((t[i],t[(i+1)%3]))) for t in triangles for i in range(3)})
    areas=[area(setup,t) for t in triangles];free=[sum(w>0 for _,w in row)>1 for row in owners]
    used={doc['bones'][i]['name'] for row in owners for i,w in row if w>0}
    budget=.1*min(math.hypot(b['x'],b['y']) for b in doc['bones'] if b['name'] in used and b.get('parent') in used)
    context=dict(row=dict(triangles=triangles),areas=areas,edges=edges,free=free,budget=budget,
        lengths=[math.dist(setup[a],setup[b]) for a,b in edges])
    result=deepcopy(doc);rows=[];keys=[]
    for frame in read(files)['animations'][name]:
        time=frame['time'];points=sample(doc,name,time)[0][slot]
        ratios=[area(points,t)/a for t,a in zip(triangles,areas)]
        fixed=[i for i,(t,r) in enumerate(zip(triangles,ratios)) if not .5<=r<=2 and all(not free[v] for v in t)]
        if fixed:
            corrected=points;solver=dict(status='fixed_vertex_counterexample',triangles=fixed)
        elif min(ratios)>=.5 and max(ratios)<=2 and all(math.dist(points[a],points[b])<=2*l for (a,b),l in zip(edges,context['lengths'])):
            corrected=points;solver=dict(status='already_within_limits')
        else:corrected,solver=refine(context,points,points,analytic=True)
        after=[area(corrected,t)/a for t,a in zip(triangles,areas)]
        rows.append(dict(time=time,before_min=min(ratios),after_min=min(after),solver=solver,
            inversions=sum(r<=0 for r in after),maximum_displacement_px=max(math.dist(a,b) for a,b in zip(points,corrected))))
        keys.append(dict(time=time,vertices=local_delta(doc,owners,matrices(doc,name,time),points,corrected)))
    result['animations'][name].setdefault('attachments',{}).setdefault('default',{}).setdefault(slot,{}).setdefault(slot,{})['deform']=keys
    return result,dict(slot=slot,budget_px=budget,rows=rows,authority='none',selected=False,
        scope='single_fixed_budget_key_pose_attempt_not_full_animation_acceptance')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('parent',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    receipt=json.loads((a.parent/'report.json').read_bytes());artifact=receipt['candidate_bundle_sha256']
    files=AnimatedStore(a.parent/'isolated-store').read(artifact)
    result,report=solve(files,'layer-004');report['parent']=artifact
    a.output.mkdir(parents=True,exist_ok=False);(a.output/'probe.json').write_bytes(canonical_bytes(report))
    if any(r['maximum_displacement_px']>1e-8 for r in report['rows']):
        stage(result,files,[r['time'] for r in report['rows']],a.output/'candidate',artifact)
    print(json.dumps(report))
