"""Recompute area correction after exact contact proposal; never auto-adopt."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.character_capture import capture
from autospine_workbench.automation.motion_target_pose import final_times
from autospine_workbench.targets.character43.support_proposal_replay import prepared_contact,without_generated_deform
from autospine_workbench.targets.character43.projected_area_adaptive import build
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import write
from autospine_workbench.targets.character43.deformation_qa import inspect
from autospine_workbench.targets.character43.motion_contacts import analyze


def run(folder,output,capture_runtime=False,foot_orientation=False,ankle_collar=False,proximal_ring=False):
    if proximal_ring and not ankle_collar:raise ValueError('proximal_ring_requires_collar')
    if ankle_collar and not foot_orientation:raise ValueError('ankle_collar_requires_foot_orientation')
    source=json.loads((folder/'report.json').read_bytes());address=source['candidate_bundle_sha256']
    files=AnimatedStore(folder/'isolated-store').read(address)
    doc=json.loads(files['skeleton.json']);name='external-motion'
    contact=json.loads(files['motion-contact.json']);evidence=json.loads(files['motion-review.json'])
    candidate=prepared_contact(doc,name,contact)
    bare=without_generated_deform(candidate,name,evidence['area_repair'])
    foot=None
    if foot_orientation:
        from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
        from autospine_workbench.targets.character43.source_foot_orientation import extract
        from autospine_workbench.targets.character43.foot_orientation_fit import fit
        identity=source['motion_identity']
        bundle=VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'],identity['bundle_sha256'])
        observed=extract(bundle);bare,foot=fit(bare,name,observed)
        foot['observations']=observed
    setup=json.loads(files['rig-setup-reference.json'])['vertices']
    output.mkdir(parents=True,exist_ok=False)
    print(json.dumps(dict(stage='post_contact_repair')),flush=True)
    repaired,correction=build(bare,name,setup,temporal=True,terminal_collar=ankle_collar,
        progress=lambda row:print(json.dumps(row),flush=True),proximal_ring=proximal_ring)
    if repaired['animations'][name]['bones']!=bare['animations'][name]['bones']:
        raise ValueError('post_contact_repair_changed_bones')
    from m4_pose_depth_recheck import recheck
    print(json.dumps(dict(stage='depth_recheck')),flush=True)
    repaired,depth=recheck(repaired,name,files,source)
    times=final_times(repaired,name,[r['time'] for r in contact.get('phase_attempt',{}).get('rows',[])])
    motion=json.loads(files['motion-ir.json']);motion['markers']=deepcopy(contact['hypothesis']['markers'])
    checked=analyze(repaired,name,motion,times,evidence['reference_length_px'])
    raw=canonical_bytes(repaired);digest=sha256(raw).hexdigest()
    isolated={n:v for n,v in files.items() if n.endswith('.png') or n=='skeleton.atlas'}
    isolated['skeleton.json']=raw
    isolated['rig-setup-reference.json']=canonical_bytes(dict(skeleton_sha256=digest,time=0,vertices=setup))
    isolated=write(isolated,dict(skeleton_sha256=digest,animations={name:[dict(time=t,vertices=sample(repaired,name,t)[0]) for t in times]}))
    qa=inspect(isolated,setup_vertices=setup)
    manifest=json.loads(files['character-manifest.json'])
    isolated['character-manifest.json']=canonical_bytes(dict(profile='post-contact-source-pose-repair-v1',
        source_candidate_sha256=address,authority='none',production_authorized=False,
        source_addresses=manifest['source_addresses'],layers=manifest['layers']))
    store=AnimatedStore(output/'isolated-store');artifact=store.publish(isolated)
    depth['skeleton_sha256']=digest
    for n,v in [('correction',correction),('contact',checked),('deformation',qa),('depth',depth)]:
        (output/(n+'.json')).write_bytes(canonical_bytes(v))
    if foot:(output/'foot-orientation.json').write_bytes(canonical_bytes(foot))
    report=dict(profile='post-contact-source-pose-repair-v1',source_candidate_sha256=address,
        candidate_bundle_sha256=artifact,authority='none',selected=False,production_authorized=False,
        contact_input_mode='preserved_selected' if contact['selected'] else 'replayed_proposal',
        sampled_frames=len(times),contact_passed=checked['passed'],
        maximum_ankle_drift_px=max(r['max_drift_px'] for r in checked['intervals']),
        original_geometry_passed=qa['passed'],sampled_inversions=sum(r['inversion_samples'] for r in qa['records']),
        projected_area_failure_samples=len(correction['refinement'][-1]['check']['failures']),
        depth_status=depth['status'],depth_scope=depth['scope'],runtime_status='not_evaluated')
    if foot:report['foot_orientation_profile']=foot['profile']
    report['correction_profile']=correction['profile']
    (output/'report.json').write_bytes(canonical_bytes(report))
    if capture_runtime:
        runtime=capture(SimpleNamespace(workspace_root=Path.cwd().parent),store,artifact,output,
            progress=lambda s:print(json.dumps(dict(stage=s)),flush=True),cancel_requested=lambda:False,storage_reference=True)
        actual=json.loads((output/'runtime/report.json').read_bytes())
        if actual['bundle_sha256']!=artifact or [r['time'] for r in actual['results']]!=times:
            raise ValueError('post_contact_capture_identity_mismatch')
        report.update(runtime_status=runtime['status'],runtime_numeric_passed=actual['passed'])
        (output/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--capture',action='store_true');p.add_argument('--foot-orientation',action='store_true')
    p.add_argument('--ankle-collar',action='store_true')
    p.add_argument('--proximal-ring',action='store_true')
    a=p.parse_args();run(a.folder,a.output,a.capture,a.foot_orientation,a.ankle_collar,a.proximal_ring)
