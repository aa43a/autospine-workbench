"""Check baked cover boundaries at the exact Runtime reference time grid."""
import argparse
import json
import math
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample,matrices
from autospine_workbench.targets.character43.deform_addition import entries
from autospine_workbench.targets.character43.numeric_reference import read


def run(source,folder,output):
    parent=json.loads((source/'report.json').read_bytes());receipt=json.loads((folder/'trial/report.json').read_bytes())
    probe=json.loads((folder/'probe.json').read_bytes());identity=parent['candidate_bundle_sha256']
    if probe['source']!=identity or receipt['parent_sha256']!=identity:raise ValueError('cover_validation_identity')
    before=json.loads(AnimatedStore(source/'isolated-store').read(identity)['skeleton.json'])
    files=AnimatedStore(folder/'trial/isolated-store').read(receipt['candidate_bundle_sha256']);after=json.loads(files['skeleton.json'])
    name='external-motion'
    if before['animations'][name]['bones']!=after['animations'][name]['bones']:raise ValueError('cover_validation_bones')
    reference=read(files)['animations'][name];setupdoc=dict(after,animations={'setup':{}})
    setup=sample(setupdoc,'setup',0)[0];rest=matrices(setupdoc,'setup',0);contexts=[]
    for row in probe['coverage']:
        slot=row['slot'];mesh=before['skins'][0]['attachments'][slot][slot]
        knees={before['bones'][i]['name'] for weights in entries(mesh) for i,w in weights if w>0 and before['bones'][i]['name'].startswith('calf_')}
        if len(knees)!=1:raise ValueError('cover_validation_joint')
        knee=knees.pop();upper=next(b['parent'] for b in before['bones'] if b['name']==knee)
        center=np.array(rest[knee][4:]);axis=center-np.array(rest[upper][4:]);axis/=np.linalg.norm(axis)
        sections=[]
        for index,sign in [(0,-1),(2,1)]:
            part=slot+'-surface-'+str(index)
            indices=[i for i,p in enumerate(setup[part]) if abs(float((np.array(p)-center)@axis)-sign*row['radius_px'])<1e-6]
            if not indices:raise ValueError('cover_validation_boundary_missing')
            sections.append((part,indices))
        contexts.append((slot,sections))
    rows=[];previous={};unselected_error=0.
    for frame in reference:
        time=frame['time'];world=frame['vertices'];old=sample(before,name,time)[0]
        for slot in set(old)&set(world):
            unselected_error=max(unselected_error,max(map(math.dist,old[slot],world[slot])))
        for slot,sections in contexts:
            points=np.array(world[slot+'-surface-1']);hull=ConvexHull(points)
            anchors=np.array([world[p][i] for p,indices in sections for i in indices])
            deficit=max(0.,float((anchors@hull.equations[:,:2].T+hull.equations[:,2]).max()))
            speed=None
            if slot in previous:
                t,p=previous[slot];speed=float(np.linalg.norm(points-p,axis=1).max()/(time-t))
            previous[slot]=(time,points)
            rows.append(dict(slot=slot,time=time,maximum_boundary_deficit_px=deficit,maximum_vertex_speed_px_s=speed))
    summary=[]
    for slot,_ in contexts:
        subset=[r for r in rows if r['slot']==slot]
        summary.append(dict(slot=slot,samples=len(subset),uncovered_samples=sum(r['maximum_boundary_deficit_px']>1e-6 for r in subset),
            worst=max(subset,key=lambda r:r['maximum_boundary_deficit_px']),maximum_vertex_speed_px_s=max(r['maximum_vertex_speed_px_s'] or 0 for r in subset)))
    result=dict(authority='none',selected=False,candidate=receipt['candidate_bundle_sha256'],summary=summary,
        unselected_vertex_error_px=unselected_error,rows=rows,
        scope='sampled_convex_boundary_coverage_not_alpha_or_continuous_time_proof')
    with output.open('xb') as f:f.write(canonical_bytes(result))
    print(json.dumps(dict(summary=summary,unselected_vertex_error_px=unselected_error)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','folder','output'):p.add_argument(n,type=Path)
    a=p.parse_args();run(a.source,a.folder,a.output)
