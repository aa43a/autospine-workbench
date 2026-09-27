"""Register accepted isolated walking evidence without replacing its baseline."""
import argparse
from hashlib import sha256
import json
import re
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_related_candidates import register
from autospine_workbench.automation.motion_related_evidence import inspect
from autospine_workbench.resolved_project import canonical_sha256
from m4_motion_cohort import api


def run(state, job, source, *, parent_state=None, unreviewed=False):
    if not re.fullmatch(r'motion-[0-9a-f]{32}', job):
        raise ValueError('invalid_motion_job_id')
    read=lambda p:json.loads(p.read_bytes())
    folder=state/'jobs/motion-intake-v1'/job
    request=read(folder/'request.json')
    receipt=read(source/'report.json');runtime=read(source/'runtime/report.json')
    accepted=None if unreviewed else read(source/'stage-review-v1.json')
    depth=read(source/'depth-review.json')
    digest=receipt['candidate_bundle_sha256']
    if accepted is not None and (accepted['candidate_bundle_sha256']!=digest or accepted['decision']!='accepted_with_exceptions'):
        raise ValueError('walking_visual_candidate_mismatch')
    for file, expected in (accepted['evidence'] if accepted is not None else {}).items():
        if file not in ('report.json','runtime/report.json','depth-review.json') or sha256((source/file).read_bytes()).hexdigest()!=expected:
            raise ValueError('walking_visual_evidence_changed')
    files=AnimatedStore(source/'isolated-store').read(digest)
    parent_files=AnimatedStore(parent_state or state).read(receipt['parent_artifact'])
    observation=json.loads(parent_files['motion-moving-ankles.json'])['source_observation']
    identity=request['motion_identity']
    if observation['source_bundle_sha256']!=identity['bundle_sha256'] or observation['motion_sha256']!=identity['clip_sha256']:
        raise ValueError('walking_source_changed')
    if files['motion-ir.json']!=parent_files['motion-ir.json']:
        raise ValueError('walking_source_motion_changed')
    raw=files['skeleton.json'];skeleton=sha256(raw).hexdigest()
    if depth['candidate_bundle_sha256']!=digest or depth['skeleton_sha256']!=skeleton:
        raise ValueError('walking_depth_changed')
    contact=json.loads(files['motion-contact.json'])
    contact.update(artifact_sha256=digest,runtime_numeric_passed=runtime['passed'])
    audit=dict(profile='corrective-contact-audit-v1',artifact_sha256=digest,
        runtime_report_sha256=canonical_sha256(runtime),moving_ankles=receipt['tracking'],contact=contact,
        authority='none',selected=False,production_authorized=False)
    linked=dict(receipt,source_identity=identity,sampled_frames=len(runtime['results']),
        contact_audit=audit,depth_audit=depth,source_request_sha256=canonical_sha256(request),
        remaining_checks=['depth','mesh_sole_contact']+(['visual'] if unreviewed else []))
    if accepted is not None:linked['source_visual_record']=accepted
    visual=None if accepted is None else dict(artifact_sha256=digest,source_motion_ir_sha256=identity['motion_ir_sha256'],
        decision=accepted['decision'],notes=accepted['notes'],source_review_sha256=canonical_sha256(accepted),
        technical_override=False,production_authorized=False,applies_to_other_candidates=False)
    inspect(request,AnimatedStore(state).read(request['character_sha256']),files,linked,runtime,visual)
    manager=SimpleNamespace(state_root=state,_lock=RLock(),projects=SimpleNamespace(workspace_root=Path.cwd().parent),
        folder=lambda _:folder,get=lambda _:api('http://127.0.0.1:8918','/api/motions/'+job))
    registration=register(manager,job,files,linked,runtime,visual)
    print(json.dumps(dict(job_id=job,registration_sha256=registration,candidate=digest)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('state',type=Path)
    p.add_argument('job');p.add_argument('source',type=Path)
    p.add_argument('--parent-state',type=Path)
    p.add_argument('--unreviewed',action='store_true',help='Register with no visual decision or imported acceptance')
    a=p.parse_args();run(a.state,a.job,a.source,parent_state=a.parent_state,unreviewed=a.unreviewed)
