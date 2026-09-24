"""Bounded local 3D repair comparison with fixed single-bone regions."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
from autospine_workbench.targets.character43.deform_addition import entries
from autospine_workbench.targets.character43.surface_projection_evidence import inspect
from autospine_workbench.targets.character43.surface_local_projection import solve


def run(surface_path,poses_path,output):
    raw=surface_path.read_bytes();surfaces=json.loads(raw);source=poses_path.read_bytes();poses=json.loads(source)
    if sha256(raw).hexdigest()!=poses['surface_sha256']:raise ValueError('corrective_surface_identity')
    result=deepcopy(poses);reports=[]
    for row in result['records']:
        s=surfaces['surfaces'][row['slot']];influences=entries({'vertices':s['source_weighted_vertices']})
        bad=[e['triangle'] for e in row['dq_evidence']['triangles'] if not e.get('intrinsic_gate_passed',False)]
        region={v for i in bad for v in s['triangles'][i]}
        seed=set(region)
        region.update(v for t in s['triangles'] if any(i in seed for i in t) for v in t)
        free=sorted(i for i in region if sum(w>.01 for b,w in influences[i])>1)
        original=row['dq_vertices'];p,report=solve(s['vertices'],original,s['triangles'],free)
        row['vertices']=original;row['evidence']=row['dq_evidence']
        row['dq_vertices']=p.tolist();row['dq_evidence']=inspect(s['vertices'],p,s['triangles'],np.eye(3))
        report.update(slot=row['slot'],time=row['time']);reports.append(report)
    result['parent_poses_sha256']=sha256(source).hexdigest();result['corrective_reports']=reports
    result['comparison_labels']=['baseline-dq','local-corrected-dq'];result['accepted']=False
    output.mkdir(parents=True,exist_ok=False)
    (output/'poses.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (output/'summary.json').write_text(json.dumps(reports,indent=2),encoding='utf-8');print(json.dumps(reports))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('surface','poses','output'):p.add_argument(key,type=Path)
    a=p.parse_args();run(a.surface,a.poses,a.output)
