"""Bake regional pose evidence and inspect interpolation without adopting it."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.regional_pose_bake import bake
from autospine_workbench.targets.character43.skirt_motion_contact import transport
from autospine_workbench.asset.planning.component_local_solver import metrics
from m4_cloth_limb_coupling_probe import coverage
from m4_skirt_waist_support import contact_change


def run(source, patch, evidence, output):
    output.mkdir(parents=True,exist_ok=False)
    receipt=json.loads((source/'report.json').read_bytes())
    files=AnimatedStore(source/'isolated-store').read(receipt['candidate_bundle_sha256'])
    report=json.loads((patch/'report.json').read_bytes())
    raw=(patch/'posed-cloth.json').read_bytes(); grid=json.loads(evidence.read_bytes())
    if (report['source_candidate']!=receipt['candidate_bundle_sha256'] or
        report['skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest() or
        report['posed_cloth_sha256']!=sha256(raw).hexdigest() or
        report['evidence_sha256']!=sha256(evidence.read_bytes()).hexdigest()):
        raise ValueError('regional_animation_identity')
    poses={float(k):v for k,v in json.loads(raw).items()}
    doc=json.loads(files['skeleton.json']); slot=grid['cloth']; name='external-motion'
    # Explicit diagnostic fade: no correction before .7 or after 1.1 seconds.
    interval=(.7,1.1); changed=bake(doc,name,slot,poses,interval)
    mesh=doc['skins'][0]['attachments'][slot][slot]
    triangles=np.asarray(mesh['triangles']).reshape(-1,3).tolist()
    setup=sample(dict(doc,animations={'setup':{}}),'setup',0)[0][slot]
    texture=Image.open(BytesIO(files['images/'+mesh.get('path',slot)+'.png'])).convert('RGBA')
    keys=changed['animations'][name]['attachments']['default'][slot][slot]['deform']
    knots=sorted({k['time'] for k in keys if interval[0]<=k['time']<=interval[1]}|set(poses)|set(interval))
    times=sorted(set(knots)|{(a+b)/2 for a,b in zip(knots,knots[1:])}|
                 {interval[0]+i/240 for i in range(97)})
    rows=[]
    for frame_index,time in enumerate(times):
        before=sample(doc,name,time)[0]; after=sample(changed,name,time)[0]
        original=before[slot]; points=after[slot]
        qa=metrics(setup,points,triangles)
        distance=max(math.dist(a,b) for a,b in zip(original,points))
        waist=contact_change(original,points,report['waist_support']['anchors'])
        # All originally covered material points stay in the denominator.
        checks=[]
        for i,g in enumerate(grid['grid']):
            if g['limb_alpha']<8 or g['source_cloth_alpha']<8:continue
            query=transport(after[grid['limb']],g['anchor'])
            alpha=coverage(mesh,points,texture,query)
            if alpha<8:checks.append(dict(sample=i,alpha=alpha))
        rows.append(dict(time=time,geometry=qa,max_offset_px=distance,waist_error_px=waist,
            uncovered=checks,passed=not qa['bad_triangles'] and qa['max_edge_stretch']<=2
            and distance<=8 and waist<=1e-7 and not checks))
        if frame_index%50==0:
            print(json.dumps(dict(stage='interpolation',completed=frame_index+1,total=len(times))),flush=True)
    encoded=canonical_bytes(changed)
    result=dict(profile='regional-cloth-animation-v1',source_candidate=report['source_candidate'],
        skeleton_sha256=sha256(encoded).hexdigest(),patch_report_sha256=sha256((patch/'report.json').read_bytes()).hexdigest(),
        rows=[dict(slot=slot)],frames=rows,validation_times=times,validation=dict(frames=len(times)),
        interval=interval,keypose_statuses=[dict(time=r['time'],status=r['status']) for r in report['frames']],
        passed=all(r['passed'] for r in rows),authority='none',selected=False,
        scope='local_animation_interpolation_not_full_character_runtime_or_visual_acceptance')
    result['pending_checks']=['visible_lower_leg_guard_over_full_interval',
        'full_character_geometry_and_official_runtime','framebuffer_and_visual_review']
    (output/'skeleton.json').write_bytes(encoded);(output/'report.json').write_bytes(canonical_bytes(result))
    print(json.dumps(dict(frames=len(rows),failed=sum(not r['passed'] for r in rows),
        coverage_failed=sum(bool(r['uncovered']) for r in rows),
        geometry_failed=sum(bool(r['geometry']['bad_triangles']) for r in rows),
        max_offset_px=max(r['max_offset_px'] for r in rows),
        max_waist_error_px=max(r['waist_error_px'] for r in rows))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','patch','evidence','output'):p.add_argument(n,type=Path)
    a=p.parse_args();run(a.source,a.patch,a.evidence,a.output)
