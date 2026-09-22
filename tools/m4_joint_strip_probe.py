"""Evaluate a setup-derived knee strip against exact failed leg poses."""
import argparse
import json
import math
from pathlib import Path
import numpy as np
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import matrices,sample
from autospine_workbench.targets.character43.deform_addition import entries
from autospine_workbench.targets.character43.transverse_frame import weighted_points,without_inherited_shear
from autospine_workbench.targets.character43.joint_material_strip import map_points,relative,jacobian_samples
from autospine_workbench.asset.planning.component_local_solver import metrics
from autospine_workbench.targets.spine43.continuous_pose import area


def run(source,output,slots,times,follow_curve=False):
    receipt=json.loads((source/'report.json').read_bytes());identity=receipt['candidate_bundle_sha256']
    files=AnimatedStore(source/'isolated-store').read(identity);doc=json.loads(files['skeleton.json'])
    duration=max(k['time'] for tracks in doc['animations']['external-motion']['bones'].values() for keys in tracks.values() for k in keys)
    if (not times or len(times)>33 or any(not math.isfinite(t) or not 0<=t<=duration for t in times)
            or not slots or len(set(slots))!=len(slots)):
        raise ValueError('joint_strip_probe_selection')
    restdoc=dict(doc,animations={'setup':{}});setup=sample(restdoc,'setup',0)[0];rest=matrices(restdoc,'setup',0)
    rows=[]
    for slot in slots:
        mesh=doc['skins'][0]['attachments'][slot][slot];influences=entries(mesh)
        owners=[{doc['bones'][i]['name'] for i,w in row if w>0} for row in influences]
        knees={n for row in owners for n in row if n.startswith('calf_')}
        if len(knees)!=1:raise ValueError('joint_strip_unique_knee_required')
        knee=knees.pop();upper=next(b['parent'] for b in doc['bones'] if b['name']==knee)
        selected=[upper,knee];center=np.array(rest[knee][4:]);hip=np.array(rest[upper][4:]);axis=center-hip
        length=np.linalg.norm(axis);axis/=length;points=setup[slot]
        mixed=[i for i,row in enumerate(owners) if upper in row and knee in row]
        if not mixed:raise ValueError('joint_strip_no_mixed_region')
        tri=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]
        edges={tuple(sorted((a,b))) for t in tri for a,b in zip(t,t[1:]+t[:1])}
        spacing=float(np.median([math.dist(points[a],points[b]) for a,b in edges]))
        span=max(abs(float((np.array(points[i])-center)@axis)) for i in mixed)+spacing
        movable=[i for i,row in enumerate(owners) if row<=set(selected) and abs(float((np.array(points[i])-center)@axis))<span]
        for time in times:
            current=matrices(doc,'external-motion',time)
            before,_=weighted_points(mesh,doc['bones'],rest,current,selected)
            frames=[relative(rest[n],without_inherited_shear(rest[n],current[n])[0]) for n in selected]
            mapped=map_points([points[i] for i in movable],center,axis,span,*frames,follow_curve=follow_curve)
            jacobians=jacobian_samples([points[i] for i in movable],center,axis,span,*frames,follow_curve=follow_curve)
            after=[p[:] for p in before]
            for i,p in zip(movable,mapped):after[i]=p
            rows.append(dict(slot=slot,time=time,half_span_px=span,upper_length_px=float(length),
                movable_vertices=len(movable),before=metrics(points,before,tri),after=metrics(points,after,tri),
                inverted=[i for i,t in enumerate(tri) if area(after,t)*area(points,t)<=0],
                mapping_fold_witnesses=[dict(vertex=i,**r) for i,r in zip(movable,jacobians) if r['negative_at_both_steps']],
                maximum_displacement_px=max(map(math.dist,before,after))))
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as f:f.write(canonical_bytes(dict(profile='joint-material-strip-probe-v1',
        source=identity,authority='none',selected=False,follow_curve=follow_curve,
        baseline='direct_transverse_no_shear_without_old_leg_deforms_not_baked_interpolation',rows=rows)))
    print(json.dumps([dict(slot=r['slot'],time=r['time'],span=r['half_span_px'],before=r['before']['inversions'],
        after=r['after']['inversions'],mapping_folds=len(r['mapping_fold_witnesses']),
        min_area=r['after']['min_area_ratio'],edge=r['after']['max_edge_stretch']) for r in rows]))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--slots',nargs='+',required=True);p.add_argument('--times',nargs='+',type=float,required=True)
    p.add_argument('--follow-curve',action='store_true')
    a=p.parse_args();run(a.source,a.output,a.slots,a.times,a.follow_curve)
