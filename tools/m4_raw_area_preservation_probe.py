"""Compare fixed floors with raw-pose preservation; never publishes a candidate."""
import argparse
from copy import deepcopy
import json
import math
from hashlib import sha256
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import matrices, sample
from autospine_workbench.targets.character43.area_preservation import from_pose
from autospine_workbench.targets.character43.area_projection import project
from autospine_workbench.targets.character43.local_area_constraints import refine
from autospine_workbench.targets.character43.projected_area_reference import reference
from autospine_workbench.targets.character43.raw_compression_preservation import CONTRACT, floors
from autospine_workbench.targets.spine43.continuous_pose import area


def run(artifact, slot, name, time, *, files=None, policies=None):
    if files is None:files=AnimatedStore(Path('workspace')).read(artifact)
    doc=json.loads(files['skeleton.json'])
    if not math.isfinite(time) or time<0:raise ValueError('invalid_time')
    keys=[k['time'] for tracks in doc['animations'][name]['bones'].values() for track in tracks.values() for k in track]
    if time>max(keys):raise ValueError('time_outside_animation')
    actual=sample(doc,name,time)[0][slot]
    raw=deepcopy(doc);raw['animations'][name].pop('attachments',None)
    raw['animations'][name].pop('deform',None)
    origin=sample(raw,name,time)[0][slot]
    rest=deepcopy(raw);rest['animations'][name]={}
    setup_reference=json.loads(files['rig-setup-reference.json'])
    if setup_reference['skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest():
        raise ValueError('setup_identity_mismatch')
    setup=setup_reference['vertices'][slot]
    mesh=doc['skins'][0]['attachments'][slot][slot]
    triangles=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]
    areas=[area(setup,t) for t in triangles]
    data=mesh['vertices'];influences=[];cursor=0
    while cursor<len(data):
        count=data[cursor];cursor+=1
        influences.append([(data[cursor+j*4],data[cursor+j*4+3]) for j in range(count)])
        cursor+=count*4
    bones=doc['bones']
    refs=reference(areas,triangles,influences,bones,matrices(rest,name,0),matrices(raw,name,time))
    used={bones[b]['name'] for entries in influences for b,w in entries if w>0}
    lengths=[math.hypot(b['x'],b['y']) for b in bones if b['name'] in used and b.get('parent') in used]
    budget=.1*min(lengths)
    edges=sorted({tuple(sorted((t[i],t[(i+1)%3]))) for t in triangles for i in range(3)})
    context=dict(row={'triangles':triangles},areas=refs,edges=edges,
        lengths=[math.dist(setup[a],setup[b]) for a,b in edges],
        free=[sum(w>0 for _,w in entries)>1 for entries in influences],budget=budget)
    raw_ratios=[area(origin,t)/a for t,a in zip(triangles,areas)]
    def metrics(points):
        ratios=[area(points,t)/a for t,a in zip(triangles,areas)]
        relative=[area(points,t)/a for t,a in zip(triangles,refs)]
        return dict(minimum_setup_ratio=min(ratios),maximum_setup_ratio=max(ratios),
            setup_area_failed=sum(not .5<=r<=2 for r in ratios),inversions=sum(r<=0 for r in ratios),
            projected_area_failed=sum(not .5<=r<=2 for r in relative),
            raw_compression_worsened=[i for i,(a,b) in enumerate(zip(ratios,raw_ratios)) if 0<b<.5 and a<b-1e-7],
            maximum_displacement_px=max(math.dist(a,b) for a,b in zip(points,origin)),
            maximum_edge_ratio=max(math.dist(points[a],points[b])/l for (a,b),l in zip(edges,context['lengths'])),
            fixed_vertex_shift=max([math.dist(a,b) for a,b,free in zip(points,origin,context['free']) if not free] or [0]),
            setup_ratios=ratios)
    results={};points_by_policy={}
    choices=('fixed_floor','preserve_raw_pose','preserve_raw_compression','dual_area_floor')
    if policies is None:policies=choices[:3]
    if not policies or any(p not in choices for p in policies):raise ValueError('unknown_probe_policy')
    for policy in policies:
        trial=deepcopy(context)
        trial['minimum_ratios']=[.5]*len(triangles) if policy=='fixed_floor' else from_pose(origin,triangles,refs)
        if policy=='preserve_raw_compression':
            trial['area_floor_contract']=CONTRACT
            trial['minimum_ratios']=floors(origin,triangles,refs,areas)
        if policy=='dual_area_floor':
            from autospine_workbench.targets.character43.dual_area_floor import floors as dual_floors
            trial['area_floor_contract']=CONTRACT
            trial['minimum_ratios']=dual_floors(areas,refs)
        points,solver=project(trial,origin)
        if not solver['converged']:
            points,solver['refinement']=refine(trial,origin,points,analytic=True,expanded=True)
        violation=[i for i,(t,r,f) in enumerate(zip(triangles,refs,trial['minimum_ratios'])) if area(points,t)/r<f-1e-7]
        results[policy]=dict(metrics(points),solver=solver,preservation_floor_failures=violation)
        points_by_policy[policy]=points
    return dict(profile='raw-area-preservation-single-pose-probe-v1',artifact_sha256=artifact,
        slot=slot,animation=name,time=time,budget_px=budget,authority='none',selected=False,
        scope='cpu_single_pose_not_runtime_or_animation_acceptance',raw=metrics(origin),actual=metrics(actual),
        policies=results,points=dict(raw=origin,actual=actual,**points_by_policy),triangles=triangles)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('artifact');parser.add_argument('slot');parser.add_argument('animation')
    parser.add_argument('time',type=float);parser.add_argument('output',type=Path)
    args=parser.parse_args();result=run(args.artifact,args.slot,args.animation,args.time)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:{f:v for f,v in row.items() if f not in ('setup_ratios','solver')} for k,row in result['policies'].items()}))
