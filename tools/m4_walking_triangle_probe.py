"""Locate calibrated walking compression without changing the geometry gate."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import numpy as np
from autospine_workbench.targets.character43.affine_pose import matrices, sample
from autospine_workbench.targets.character43.deform_addition import entries
from autospine_workbench.targets.character43.triangle_shape_evidence import build
from autospine_workbench.resolved_project import canonical_sha256


def run(path, output):
    doc=json.loads(path.read_text(encoding='utf-8'))
    name=next(iter(doc['animations']))
    rest=deepcopy(doc);rest['animations'][name]={'bones':{}}
    base=sample(rest,name,0)[0];setup=matrices(rest,name,0)
    times=sorted({k.get('time',0) for row in doc['animations'][name]['bones'].values() for keys in row.values() for k in keys})
    times=sorted(set(times)|{(a+b)/2 for a,b in zip(times,times[1:])})
    meshes=doc['skins'][0]['attachments'];failed={}
    def areas(points,triangles):
        p=np.asarray(points)[triangles];a=p[:,1]-p[:,0];b=p[:,2]-p[:,0]
        return (a[:,0]*b[:,1]-a[:,1]*b[:,0])/2
    triangles={slot:np.asarray(choices[slot]['triangles']).reshape(-1,3) for slot,choices in meshes.items()}
    initial={s:areas(base[s],triangles[s]) for s in meshes}
    for time in times:
        points=sample(doc,name,time)[0]
        for slot,tri in triangles.items():
            ratios=areas(points[slot],tri)/initial[slot]
            for index in np.flatnonzero(ratios<.5):
                key=(slot,int(index));value=float(ratios[index])
                if key not in failed or value<failed[key]['area_ratio']:
                    failed[key]=dict(slot=slot,triangle=int(index),time=time,area_ratio=value,
                        indices=tri[index].tolist(),setup=[base[slot][i] for i in tri[index]],
                        actual=[points[slot][i] for i in tri[index]])
    for row in failed.values():
        mesh=meshes[row['slot']][row['slot']];weights=entries(mesh)
        row['shape']=build(row['setup'],row['actual'],row['actual'],
            [weights[i] for i in row['indices']],doc['bones'],setup,matrices(doc,name,row['time']))
    report=dict(skeleton_sha256=canonical_sha256(doc),samples=len(times),selected=False,authority='none',
        rows=sorted(failed.values(),key=lambda r:r['area_ratio']),
        scope='compression_locations_and_bone_shape_not_causal_proof_or_acceptance')
    with output.open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2)
    print(json.dumps(dict(samples=len(times),triangles=len(failed),worst=report['rows'][:2])))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.input,a.output)
