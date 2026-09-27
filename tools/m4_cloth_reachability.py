"""Check retained uncovered material points against the unchanged vertex budget."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from PIL import Image
import numpy as np
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.material_reachability import inspect


def run(source,neighborhood,patch,output):
    receipt=json.loads((source/'report.json').read_bytes())
    files=AnimatedStore(source/'isolated-store').read(receipt['candidate_bundle_sha256'])
    evidence=json.loads(neighborhood.read_bytes());trial=json.loads((patch/'report.json').read_bytes())
    if (trial['source_candidate']!=receipt['candidate_bundle_sha256'] or
        trial['source_candidate']!=evidence['candidate_bundle_sha256'] or
        trial['skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest() or
        trial['evidence_sha256']!=sha256(neighborhood.read_bytes()).hexdigest() or
        trial['posed_cloth_sha256']!=sha256((patch/'posed-cloth.json').read_bytes()).hexdigest()):
        raise ValueError('cloth_reachability_identity')
    doc=json.loads(files['skeleton.json']);slot=evidence['cloth'];mesh=doc['skins'][0]['attachments'][slot][slot]
    alpha=np.asarray(Image.open(BytesIO(files['images/'+mesh.get('path',slot)+'.png'])).convert('RGBA').getchannel('A'),float)
    rows=[]
    for frame in trial['frames']:
        failed=[r for r in frame.get('coverage',[]) if not r['passed'] and r['required_coverage']]
        if not failed:continue
        original=next(r for r in evidence['frames'] if r['time']==frame['time'])
        points=sample(doc,'external-motion',frame['time'])[0][slot]
        for row in failed:
            query=next(r['world'] for r in original['rows'] if r['sample']==row['sample'])
            for threshold in (8,128):
                check=inspect(mesh,points,alpha,query,budget=trial['limits']['vertex_displacement_px'],threshold=threshold)
                rows.append(dict(time=frame['time'],material_sample=row['sample'],query=query,**check))
                print(json.dumps({k:rows[-1][k] for k in ('time','material_sample','threshold','status','conservative_distance_lower_bound_px')}),flush=True)
    report=dict(profile='cloth-material-budget-reachability-v1',rows=rows,source_candidate=trial['source_candidate'],
        skeleton_sha256=trial['skeleton_sha256'],patch_report_sha256=sha256((patch/'report.json').read_bytes()).hexdigest(),
        authority='none',selected=False,scope='single_material_point_necessary_condition_not_full_patch_or_runtime')
    with output.open('xb') as stream:stream.write(canonical_bytes(report))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','neighborhood','patch','output'):p.add_argument(name,type=Path)
    a=p.parse_args();run(a.source,a.neighborhood,a.patch,a.output)
