"""Check extremal exposed material points against joint repair budgets."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import numpy as np
from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.joint_coverage_bound import check


def run(runtime,region,patch,output):
    with output.open('xb') as handle:handle.write(b'{}')
    receipt=json.loads((runtime/'report.json').read_bytes())
    files=AnimatedStore(runtime/'isolated-store').read(receipt['candidate_bundle_sha256'])
    source=json.loads((region/'report.json').read_bytes());details=json.loads((region/'before.json').read_bytes())
    trial=json.loads((patch/'report.json').read_bytes())
    if (source['skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest() or
        trial['skeleton_sha256']!=source['skeleton_sha256'] or trial['time']!=source['time'] or
        source['inputs'][str(patch/'report.json')]!=sha256((patch/'report.json').read_bytes()).hexdigest()):
        raise ValueError('exposure_bound_identity')
    rows=[r for r in details['rows'] if r['newly_exposed']]
    if not rows:raise ValueError('exposure_bound_empty')
    chosen={}
    for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
        row=max(rows,key=lambda r:dx*r['world'][0]+dy*r['world'][1]);chosen[tuple(row['pixel'])]=row
    doc=json.loads(files['skeleton.json']);slot=trial['cloth'];mesh=doc['skins'][0]['attachments'][slot][slot]
    points=sample(doc,'external-motion',source['time'])[0][slot]
    alpha=np.asarray(Image.open(BytesIO(files['images/'+mesh.get('path',slot)+'.png'])).convert('RGBA').getchannel('A'),float)
    checks=[dict(pixel=r['pixel'],source_material=r['source'],**check(mesh,points,alpha,r['world'])) for r in chosen.values()]
    rejected=[r for r in checks if r['status']=='outside_joint_displacement_budget']
    result=dict(time=source['time'],skeleton_sha256=source['skeleton_sha256'],checks=checks,
        status='local_repair_insufficient' if rejected else 'not_ruled_out',
        rejected_witnesses=len(rejected),tested_extreme_points=len(checks),region_points=len(rows),
        scope='extreme_point_counterexamples_not_full_region_feasibility_or_pose_acceptance',
        next_route='pose_or_view_representation_review' if rejected else 'region_solver_required',
        authority='none',selected=False,inputs={str(p):sha256(p.read_bytes()).hexdigest() for p in (region/'report.json',region/'before.json',patch/'report.json')})
    output.write_bytes(canonical_bytes(result))
    print(json.dumps({k:result[k] for k in ('status','rejected_witnesses','tested_extreme_points','region_points','next_route')}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('runtime','region','patch','output'):p.add_argument(n,type=Path)
    a=p.parse_args();run(a.runtime,a.region,a.patch,a.output)
