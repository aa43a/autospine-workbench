"""Capture exact calibrated walking repair; all prior Runtime evidence is discarded."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.character_capture import capture
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.motion_target_pose import final_times
from autospine_workbench.automation.motion_moving_ankles import check
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import write
from autospine_workbench.targets.character43.deformation_qa import inspect
from autospine_workbench.targets.character43.final_motion_contact import recheck
from autospine_workbench.resolved_project import canonical_sha256
from m4_experiment_player_export import export


def run(parent, repair, contact_path, output, artifact_state=Path('workspace')):
    files=AnimatedStore(artifact_state).read(parent)
    document=json.loads((repair/'skeleton.json').read_bytes())
    repaired=json.loads((repair/'report.json').read_bytes())
    contact_report=json.loads(contact_path.read_bytes())
    if canonical_sha256(document)!=repaired['skeleton_sha256'] or not repaired['geometry']['passed']:
        raise ValueError('repair_evidence_mismatch')
    if repaired['parent_sha256']!=contact_report['final_check']['skeleton_sha256']:
        raise ValueError('repair_parent_mismatch')
    original=json.loads(files['skeleton.json'])
    if {k:v for k,v in original.items() if k!='animations'}!={k:v for k,v in document.items() if k!='animations'}:
        raise ValueError('walking_setup_changed')
    name='external-motion'
    times=final_times(document,name,[r['time'] for r in contact_report['rows']])
    reference=json.loads(files['motion-moving-ankles.json'])['final_check']['limit_px']/.01
    tracking=check(document,name,contact_report,times,reference)
    if not tracking['passed']:raise ValueError('walking_tracking_failed')
    motion=json.loads(files['motion-ir.json'])
    contact=recheck(document,name,motion,json.loads(files['motion-contact.json']),times,reference)
    raw=canonical_bytes(document)
    isolated={k:v for k,v in files.items() if k.endswith('.png') or k=='skeleton.atlas'}
    isolated['skeleton.json']=raw
    setup=json.loads(files['rig-setup-reference.json']);setup['skeleton_sha256']=sha256(raw).hexdigest()
    isolated['rig-setup-reference.json']=canonical_bytes(setup)
    isolated=write(isolated,dict(skeleton_sha256=sha256(raw).hexdigest(),animations={name:[
        dict(time=t,vertices=sample(document,name,t)[0]) for t in times]}))
    qa=inspect(isolated,setup_vertices=setup['vertices'])
    if not qa['passed']:raise ValueError('walking_geometry_failed')
    isolated.update({'deformation.json':canonical_bytes(qa),'motion-contact.json':canonical_bytes(contact),
                     'motion-ir.json':canonical_bytes(motion),'walking-tracking.json':canonical_bytes(tracking)})
    manifest=json.loads(files['character-manifest.json'])
    manifest.update(status='needs_review',files={k:sha256(v).hexdigest() for k,v in isolated.items()})
    isolated['character-manifest.json']=canonical_bytes(manifest)
    output.mkdir()
    store=AnimatedStore(output/'isolated-store');digest=store.publish(isolated)
    receipt=dict(candidate_bundle_sha256=digest,parent_artifact=parent,geometry_passed=True,
        tracking=tracking,contact_status=contact['status'],depth_status='not_evaluated_for_new_skeleton',
        runtime_status='pending',authority='none',selected=False,production_authorized=False)
    (output/'report.json').write_bytes(canonical_bytes(receipt))
    result=capture(SimpleNamespace(workspace_root=Path.cwd().parent),store,digest,output,
        progress=lambda stage:print(stage,flush=True),cancel_requested=lambda:False,storage_reference=True)
    receipt.update(runtime_status=result['status'],runtime_frames=result.get('frames'))
    (output/'report.json').write_bytes(canonical_bytes(receipt))
    if (output/'runtime/report.json').exists():
        runtime=json.loads((output/'runtime/report.json').read_bytes())
        if runtime.get('passed') is True:export(output)
    print(json.dumps(receipt),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent')
    for key in ('repair','contact','output'):p.add_argument(key,type=Path)
    p.add_argument('--artifact-state',type=Path,default=Path('workspace'))
    a=p.parse_args();run(a.parent,a.repair,a.contact,a.output,a.artifact_state)
