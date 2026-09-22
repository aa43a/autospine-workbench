"""Rebuild a verified support sequence through mesh, depth, and official Runtime."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from m4_direction_stage_probe import load_stages
from m4_support_window_verify import verify
from m4_pose_depth_recheck import recheck
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.character_capture import capture
from m4_support_capture_grid import build as capture_grid
from autospine_workbench.targets.character43.support_row_tracks import apply
from autospine_workbench.targets.character43.foot_orientation_fit import fit
from autospine_workbench.targets.character43.projected_area_adaptive import build
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import write
from autospine_workbench.targets.character43.deformation_qa import inspect
from autospine_workbench.targets.character43.motion_contacts import analyze


def run(folder,output,capture_runtime=False):
    sequence=json.loads((folder/'report.json').read_bytes());job=sequence['job_id']
    fitted,final,pose,evidence,files,address,motion=load_stages(job)
    if address!=sequence['parent_artifact_sha256'] or not sequence['ready_for_mesh_rebuild']:
        raise ValueError('support_rebuild_identity_or_eligibility_changed')
    contact=json.loads(files['motion-contact.json']);name='external-motion'
    verification=verify(fitted,final,motion,pose,contact,sequence,evidence['reference_length_px'])
    if not verification['contact_after']['passed'] or not verification['contact_not_increased'] or not verification['support_limits_passed']:
        raise ValueError('support_rebuild_verification_failed')
    bare=apply(fitted,name,sequence['candidate_rows'])
    bare,foot=fit(bare,name,evidence['post_contact_repair']['observations'])
    setup=json.loads(files['rig-setup-reference.json'])['vertices']
    output.mkdir(parents=True,exist_ok=False)
    repaired,correction=build(bare,name,setup,temporal=True,terminal_collar=True,proximal_ring=True,
        preserve_area=True,repair_band=True,fixed_band=True,interpolation_margin=True,
        progress=lambda r:print(json.dumps(r),flush=True))
    if repaired['animations'][name]['bones']!=bare['animations'][name]['bones']:
        raise ValueError('support_rebuild_changed_bone_tracks')
    request=json.loads((Path('workspace/jobs/motion-intake-v1')/job/'request.json').read_bytes())
    repaired,depth=recheck(repaired,name,files,request)
    times=capture_grid(repaired,name,sequence)
    measured=deepcopy(motion);measured['markers']=deepcopy(contact['hypothesis']['markers'])
    checked=analyze(repaired,name,measured,times,evidence['reference_length_px'])
    old=analyze(final,name,measured,times,evidence['reference_length_px'])
    raw=canonical_bytes(repaired);digest=sha256(raw).hexdigest()
    isolated={n:v for n,v in files.items() if n.endswith('.png') or n=='skeleton.atlas'}
    isolated['skeleton.json']=raw
    isolated['rig-setup-reference.json']=canonical_bytes(dict(skeleton_sha256=digest,time=0,vertices=setup))
    isolated=write(isolated,dict(skeleton_sha256=digest,animations={name:[dict(time=t,vertices=sample(repaired,name,t)[0]) for t in times]}))
    qa=inspect(isolated,setup_vertices=setup)
    manifest=json.loads(files['character-manifest.json'])
    isolated['character-manifest.json']=canonical_bytes(dict(profile='support-window-rebuild-v1-experiment',
        source_candidate_sha256=address,authority='none',production_authorized=False,
        source_addresses=manifest['source_addresses'],layers=manifest['layers']))
    store=AnimatedStore(output/'isolated-store');artifact=store.publish(isolated)
    for n,v in [('correction',correction),('contact',checked),('deformation',qa),('depth',depth),('foot-orientation',foot)]:
        (output/(n+'.json')).write_bytes(canonical_bytes(v))
    report=dict(profile='support-window-rebuild-v1-experiment',source_job_id=job,source_candidate_sha256=address,
        source_sequence_sha256=sha256(canonical_bytes(sequence)).hexdigest(),
        capture_times_sha256=sha256(canonical_bytes(times)).hexdigest(),
        candidate_bundle_sha256=artifact,authority='none',selected=False,production_authorized=False,
        geometry_passed=qa['passed'],contact_passed=checked['passed'],sampled_frames=len(times),
        maximum_ankle_drift_px=checked['max_drift_px'],old_maximum_ankle_drift_px=old['max_drift_px'],
        contact_not_increased=checked['max_drift_px']<=old['max_drift_px'],
        constraint_failures=len(correction['refinement'][-1]['check']['failures']),
        depth_status=depth['status'],runtime_status='not_evaluated')
    (output/'report.json').write_bytes(canonical_bytes(report))
    if capture_runtime:
        runtime=capture(SimpleNamespace(workspace_root=Path.cwd().parent),store,artifact,output,
            progress=lambda s:print(json.dumps(dict(stage=s)),flush=True),cancel_requested=lambda:False,storage_reference=True)
        actual=json.loads((output/'runtime/report.json').read_bytes())
        if actual['bundle_sha256']!=artifact or [r['time'] for r in actual['results']]!=times:
            raise ValueError('support_rebuild_capture_identity_mismatch')
        report.update(runtime_status=runtime['status'],runtime_numeric_passed=actual['passed'])
        (output/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--capture',action='store_true');a=p.parse_args();run(a.folder,a.output,a.capture)
