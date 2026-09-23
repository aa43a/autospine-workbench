"""Isolated observed hand-axis candidate; never overwrite accepted artifacts."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.motion_validation import motion_ir_sha256
from autospine_workbench.targets.character43.source_hand_axis import extract
from autospine_workbench.targets.character43.source_pose_fit import fit
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.deform_addition import entries
from m4_squat_stage_players import stage,shared_camera


def candidate(document,observed):
    name='external-motion';hands={'hand_l','hand_r'}
    stripped=deepcopy(document);animation=stripped['animations'][name]
    if animation.get('deform'):raise ValueError('hand_candidate_legacy_deform')
    old=animation.pop('attachments',{})
    fitted,evidence=fit(stripped,name,observed['vectors'],observed['times'],project_lengths=True,include_hands=True)
    affected=[]
    for slot,choices in document['skins'][0]['attachments'].items():
        mesh=choices[slot]
        if len(mesh['vertices'])==len(mesh['uvs']):raise ValueError('hand_candidate_unweighted_unsupported')
        used={document['bones'][i]['name'] for row in entries(mesh) for i,w in row if w>0}
        if used&hands:affected.append(slot)
    retained=deepcopy(old)
    for skin in retained.values():
        for slot in affected:
            for tracks in skin.get(slot,{}).values():tracks.pop('deform',None)
    if retained:fitted['animations'][name]['attachments']=retained
    for bone,tracks in document['animations'][name]['bones'].items():
        if bone not in hands and fitted['animations'][name]['bones'][bone]!=tracks:
            raise ValueError('hand_candidate_changed_upstream')
    errors=[]
    times=sorted(set(observed['times'])|{(a+b)/2 for a,b in zip(observed['times'],observed['times'][1:])})
    for t in times:
        before,after=(matrices(d,name,t) for d in (document,fitted))
        errors.extend(math.dist(before[h][4:],after[h][4:]) for h in hands)
    return fitted,dict(fit=evidence,affected_slots=affected,maximum_wrist_displacement_px=max(errors),
        preserved_upstream_channels=True,removed_stale_deform_only_on_hand_influenced_slots=True,
        authority='none',selected=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('artifact');p.add_argument('clip');p.add_argument('bundle');p.add_argument('output',type=Path)
    a=p.parse_args();files=AnimatedStore(Path('workspace')).read(a.artifact)
    bundle=VerifiedMotionBundleReader(Path('workspace')).load(a.clip,a.bundle)
    if json.loads(files['motion-review.json'])['motion_sha256']!=motion_ir_sha256(bundle.motion):
        raise ValueError('hand_candidate_source_mismatch')
    observed=extract(bundle);doc=json.loads(files['skeleton.json'])
    result,report=candidate(doc,observed)
    a.output.mkdir(parents=True,exist_ok=False)
    report.update(parent=a.artifact,clip=a.clip,bundle=a.bundle,observations=observed)
    (a.output/'probe.json').write_bytes(canonical_bytes(report))
    times=[observed['times'][0],observed['times'][len(observed['times'])//2],observed['times'][-1]]
    stage(doc,files,times,a.output/'baseline',a.artifact)
    stage(result,files,times,a.output/'hand',a.artifact)
    shared_camera(a.output,('baseline','hand'))
    print(json.dumps({k:v for k,v in report.items() if k not in ('fit','observations')}))
