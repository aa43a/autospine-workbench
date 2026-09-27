"""Measure full limb coverage before and after a rejected point-only repair."""
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
from autospine_workbench.targets.character43.material_exposure_region import inspect


def run(runtime,patch,output):
    output.mkdir(parents=True,exist_ok=False)
    receipt=json.loads((runtime/'report.json').read_bytes())
    files=AnimatedStore(runtime/'isolated-store').read(receipt['candidate_bundle_sha256'])
    report=json.loads((patch/'report.json').read_bytes());doc=json.loads(files['skeleton.json'])
    if sha256(files['skeleton.json']).hexdigest()!=report['skeleton_sha256']:raise ValueError('exposure_region_identity')
    limb,cloth=report['limb'],report['cloth'];time=report['time'];attachments=doc['skins'][0]['attachments']
    lm,cm=attachments[limb][limb],attachments[cloth][cloth]
    def alpha(mesh,slot):return np.asarray(Image.open(BytesIO(files['images/'+mesh.get('path',slot)+'.png'])).convert('RGBA').getchannel('A'),float)
    setup=sample(dict(doc,animations={'setup':{}}),'setup',0)[0]
    posed=sample(doc,'external-motion',time)[0];trial=json.loads((patch/'posed-limb.json').read_bytes())[str(time)]
    summaries={};regions={}
    for name,points in (('before',posed[limb]),('trial',trial)):
        evidence=inspect(lm,setup[limb],points,alpha(lm,limb),cm,setup[cloth],posed[cloth],alpha(cm,cloth))
        (output/(name+'.json')).write_bytes(canonical_bytes(evidence));summaries[name]=evidence['summary']
        regions[name]={tuple(r['pixel']) for r in evidence['rows'] if r['newly_exposed']}
        print(json.dumps(dict(stage=name,**evidence['summary'])),flush=True)
    result=dict(time=time,skeleton_sha256=report['skeleton_sha256'],summaries=summaries,
        pixels_removed=len(regions['before']-regions['trial']),pixels_added=len(regions['trial']-regions['before']),
        pixels_remaining=len(regions['before']&regions['trial']),authority='none',selected=False,
        inputs={str(p):sha256(p.read_bytes()).hexdigest() for p in (patch/'report.json',patch/'posed-limb.json')},
        scope='cpu_two_attachment_region_comparison_not_render_or_semantic_acceptance')
    (output/'report.json').write_bytes(canonical_bytes(result));print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('runtime','patch','output'):p.add_argument(n,type=Path)
    a=p.parse_args();run(a.runtime,a.patch,a.output)
