"""Diagnose residual corrective failures and test one same-budget constrained solve."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.deform_addition import entries
from autospine_workbench.targets.character43.local_area_constraints import refine
from autospine_workbench.targets.character43.numeric_reference import read
from autospine_workbench.targets.spine43.continuous_pose import area


def run(files):
    report=json.loads(files['motion-repair.json']);slot=report['slot'];name=report['animation']
    doc=json.loads(files['skeleton.json']);mesh=doc['skins'][0]['attachments'][slot][slot]
    triangles=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]
    setup=json.loads(files['rig-setup-reference.json'])['vertices'][slot]
    areas=[area(setup,t) for t in triangles]
    owners=entries(mesh);free=[sum(w>0 for _,w in row)>1 for row in owners]
    bones=doc['bones'];used={bones[i]['name'] for row in owners for i,w in row if w>0}
    budget=.1*min(math.hypot(b['x'],b['y']) for b in bones if b['name'] in used and b.get('parent') in used)
    edges=sorted({tuple(sorted((t[i],t[(i+1)%3]))) for t in triangles for i in range(3)})
    context=dict(row={'triangles':triangles},areas=areas,edges=edges,
        lengths=[math.dist(setup[a],setup[b]) for a,b in edges],free=free,budget=budget)
    raw=deepcopy(doc);del raw['animations'][name]['attachments']['default'][slot]
    keys={k['time'] for k in doc['animations'][name]['attachments']['default'][slot][slot]['deform']}
    rows=[]
    for frame in read(files)['animations'][name]:
        points=frame['vertices'][slot];ratios=[area(points,t)/a for t,a in zip(triangles,areas)]
        failed=[i for i,r in enumerate(ratios) if not .5<=r<=2]
        if not failed:continue
        time=frame['time'];origin=sample(raw,name,time)[0][slot]
        records=[]
        for index in failed:
            tri=triangles[index];movable=[v for v in tri if free[v]]
            bound=None
            if len(movable)==1:
                fixed=[v for v in tri if not free[v]]
                bound=area(origin,tri)/areas[index]+budget*math.dist(origin[fixed[0]],origin[fixed[1]])/(2*abs(areas[index]))
            records.append(dict(triangle=index,ratio=ratios[index],movable_vertices=movable,
                displacement_px=[math.dist(origin[v],points[v]) for v in tri],single_free_area_upper_bound=bound))
        corrected,solver=refine(context,origin,points,analytic=True)
        after=[area(corrected,t)/a for t,a in zip(triangles,areas)]
        rows.append(dict(time=time,at_key=time in keys,before_min=min(ratios),after_min=min(after),
            after_failed=sum(not .5<=r<=2 for r in after),solver=solver,failures=records,
            max_displacement=max(math.dist(a,b) for a,b in zip(origin,corrected))))
    return dict(slot=slot,animation=name,budget_px=budget,records=rows,authority='none',selected=False,
                scope='same_budget_key_pose_constraint_probe_not_continuous_or_runtime_acceptance')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('artifact');p.add_argument('output',type=Path);a=p.parse_args()
    report=run(AnimatedStore(Path('workspace')).read(a.artifact));report['artifact_sha256']=a.artifact
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps(dict(frames=len(report['records']),solved=sum(r['after_failed']==0 for r in report['records']),
                         budget=report['budget_px'],statuses=[r['solver']['status'] for r in report['records']])))
