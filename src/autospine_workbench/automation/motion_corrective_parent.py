"""Chain independent, topology-preserving corrections with exact provenance."""
from hashlib import sha256
import json
from ..resolved_project import canonical_sha256
from ..targets.character43.final_leg_repair_policy import PROFILE, execution_profile, verify as verify_leg
from ..targets.character43.garment_follow_scope import PROFILE as GARMENT_PROFILE
from ..targets.character43.limb_transverse_scope import PROFILE as TRANSVERSE_PROFILE
from .pipeline_run import PipelineRunError

PROFILES = {PROFILE, GARMENT_PROFILE, TRANSVERSE_PROFILE}


def verify(manager, job, request, row, artifact):
    parent = request.get('repair_execution')
    if not parent or parent.get('profile') not in PROFILES: return None
    profile = execution_profile(row, {'garment_follow':GARMENT_PROFILE,
                                      'transverse_repair':TRANSVERSE_PROFILE}.get(row['action']))
    if (profile not in PROFILES or row['slot']==parent['draft']['slot']
            or row['animation']!=parent['draft']['animation']):
        raise PipelineRunError('motion_repair_nested_execution_unsupported')
    from .motion_target_jobs import context
    result, files = context(manager, job)
    raw = files.get('motion-repair-provenance.json')
    if result['artifact_sha256']!=artifact or raw is None:
        raise PipelineRunError('motion_corrective_parent_changed')
    provenance = json.loads(raw)
    if (any(provenance.get(k)!=v for k,v in parent.items())
            or canonical_sha256(provenance['draft'])!=provenance['draft_sha256']
            or json.loads(files['motion-repair.json'])['profile']!=parent['profile']):
        raise PipelineRunError('motion_corrective_parent_changed')
    if profile==PROFILE: verify_leg(files, row)
    expected=sha256(raw).hexdigest()
    from .motion_repair_lineage import carry
    carry(files, dict(parent_job_id=job,parent_artifact_sha256=artifact,parent_repair_sha256=expected))
    for name, value in files.items():
        if name.startswith('repair-history/'):
            previous=json.loads(value)['provenance']
            if previous.get('profile') in PROFILES and previous['draft']['slot']==row['slot']:
                raise PipelineRunError('motion_corrective_slot_already_processed')
    return expected
