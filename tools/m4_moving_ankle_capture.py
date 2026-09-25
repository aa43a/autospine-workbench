"""Capture an independently checked moving-ankle proposal as an isolated candidate."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.character_capture import capture
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.motion_target_pose import final_times
from autospine_workbench.targets.character43.numeric_reference import write
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.deformation_qa import inspect
from m4_experiment_player_export import export


def run(source, proposal, validation, output):
    report = json.loads(proposal.read_bytes())
    checked = json.loads(validation.read_bytes())
    document = json.loads(proposal.with_suffix('.candidate.json').read_bytes())
    raw = canonical_bytes(document)
    parent = report['artifact_sha256']
    files = AnimatedStore(source/'isolated-store').read(parent)
    if (report['status'] != 'candidate' or checked['artifact_sha256'] != parent
            or checked['candidate_skeleton_sha256'] != sha256(raw).hexdigest()
            or not checked['geometry']['passed']
            or checked['endpoint_worst']['error'] > checked['endpoint_limit']):
        raise ValueError('moving_ankle_validation_required')
    original = json.loads(files['skeleton.json'])
    if {k:v for k,v in original.items() if k!='animations'} != {k:v for k,v in document.items() if k!='animations'}:
        raise ValueError('moving_ankle_setup_changed')
    times = final_times(document,'external-motion',[r['time'] for r in report['rows']])
    isolated = {k:v for k,v in files.items() if k.endswith('.png') or k in
                ('skeleton.atlas','character-manifest.json','motion-torso-reference.json')}
    isolated['skeleton.json'] = raw
    isolated['moving-source-ankle.json'] = canonical_bytes(report)
    setup = json.loads(files['rig-setup-reference.json'])
    setup['skeleton_sha256'] = sha256(raw).hexdigest()
    isolated['rig-setup-reference.json'] = canonical_bytes(setup)
    isolated = write(isolated,dict(skeleton_sha256=sha256(raw).hexdigest(),animations={
        'external-motion':[dict(time=t,vertices=sample(document,'external-motion',t)[0]) for t in times]}))
    qa = inspect(isolated,setup_vertices=setup['vertices'])
    if not qa['passed']:raise ValueError('moving_ankle_geometry_failed')
    output.mkdir(parents=True,exist_ok=False)
    store = AnimatedStore(output/'isolated-store');digest=store.publish(isolated)
    receipt = dict(profile='moving-source-ankle-capture-v1',candidate_bundle_sha256=digest,
        source_candidate_sha256=parent,source_identity=json.loads(files['motion-torso-reference.json'])['source_identity'],
        geometry_passed=True,sampled_frames=len(times),selected=False,authority='none',production_authorized=False)
    (output/'report.json').write_bytes(canonical_bytes(receipt))
    result = capture(SimpleNamespace(workspace_root=Path.cwd().parent),store,digest,output,
        progress=lambda stage:print(stage,flush=True),cancel_requested=lambda:False,storage_reference=True)
    receipt['runtime_status']=result['status']
    (output/'report.json').write_bytes(canonical_bytes(receipt))
    if (output/'runtime/report.json').exists():export(output)
    print(json.dumps(dict(candidate=digest,status=result['status'],frames=result.get('frames'))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','proposal','validation','output'):p.add_argument(key,type=Path)
    a=p.parse_args();run(a.source,a.proposal,a.validation,a.output)
