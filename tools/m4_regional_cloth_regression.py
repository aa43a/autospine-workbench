"""Compare continuous material coverage and protected visible limb points."""
import argparse
from hashlib import sha256
import json
from io import BytesIO
from pathlib import Path
import numpy as np
from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.material_alpha_batch import sample as alpha_sample
from autospine_workbench.targets.character43.skirt_motion_contact import locate,transport


def run(source,experiment,evidence,guards,output):
    # Fail before expensive work when the requested output cannot be created.
    with output.open('xb') as handle:handle.write(b'{}')
    receipt=json.loads((source/'report.json').read_bytes())
    files=AnimatedStore(source/'isolated-store').read(receipt['candidate_bundle_sha256'])
    report=json.loads((experiment/'report.json').read_bytes())
    grid=json.loads(evidence.read_bytes()); guard=json.loads(guards.read_bytes())
    raw=(experiment/'skeleton.json').read_bytes()
    if (report['source_candidate']!=receipt['candidate_bundle_sha256'] or
        report['skeleton_sha256']!=sha256(raw).hexdigest() or
        any(grid[k]!=guard[k] for k in ('candidate_bundle_sha256','skeleton_sha256','cloth','limb')) or
        grid['candidate_bundle_sha256']!=report['source_candidate'] or
        grid['skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest()):
        raise ValueError('regional_regression_identity')
    before=json.loads(files['skeleton.json']); after=json.loads(raw)
    slot=grid['cloth']; limb=grid['limb'];mesh=before['skins'][0]['attachments'][slot][slot]
    alpha=np.asarray(Image.open(BytesIO(files['images/'+mesh.get('path',slot)+'.png'])).convert('RGBA').getchannel('A'),float)
    setup=sample(dict(before,animations={'setup':{}}),'setup',0)[0][limb]
    triangles=before['skins'][0]['attachments'][limb][limb]['triangles']
    protected=[locate(setup,triangles,r['source_material_world']) for r in guard['rows']
               if r['exposure_kind']=='previously_visible_limb_material']
    if not protected:raise ValueError('regional_regression_guard_missing')
    targets=[(i,g['anchor']) for i,g in enumerate(grid['grid']) if g['limb_alpha']>=8 and g['source_cloth_alpha']>=8]
    rows=[]
    for frame in report['frames']:
        t=frame['time']; a=sample(before,'external-motion',t)[0];b=sample(after,'external-motion',t)[0]
        if a[limb]!=b[limb]:raise ValueError('regional_regression_limb_changed')
        queries=[transport(a[limb],anchor) for _,anchor in targets]+[transport(a[limb],p) for p in protected]
        av=alpha_sample(mesh,a[slot],alpha,queries);bv=alpha_sample(mesh,b[slot],alpha,queries)
        restored=[];new=[];remaining=[]
        for (i,_),x,y in zip(targets,av,bv):
            if x<8<=y:restored.append(i)
            elif y<8<=x:new.append(i)
            elif x<8 and y<8:remaining.append(i)
        protections=[dict(before=x,after=y,passed=y<8 if x<8 else y<=x+1e-7)
                     for x,y in zip(av[len(targets):],bv[len(targets):])]
        expected={r['sample'] for r in frame['uncovered']}
        if set(new+remaining)!=expected:raise ValueError('regional_regression_coverage_disagrees')
        rows.append(dict(time=t,restored=restored,newly_uncovered=new,remaining_uncovered=remaining,guards=protections))
    summary=dict(times=len(rows),protected_material_points=len(protected),
        newly_uncovered_times=sum(bool(r['newly_uncovered']) for r in rows),
        restored_sample_times=sum(len(r['restored']) for r in rows),
        remaining_uncovered_times=sum(bool(r['remaining_uncovered']) for r in rows),
        guard_failed_times=sum(any(not g['passed'] for g in r['guards']) for r in rows))
    result=dict(summary=summary,rows=rows,source_candidate=report['source_candidate'],
        skeleton_sha256=report['skeleton_sha256'],authority='none',selected=False,
        inputs={str(p):sha256(p.read_bytes()).hexdigest() for p in (evidence,guards,experiment/'report.json')},
        scope='sampled_material_alpha_not_whole_limb_occlusion_or_framebuffer_acceptance')
    output.write_bytes(canonical_bytes(result));print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','experiment','evidence','guards','output'):p.add_argument(n,type=Path)
    a=p.parse_args();run(a.source,a.experiment,a.evidence,a.guards,a.output)
