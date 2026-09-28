"""Select an exact registered body for M5 without replacing its parent job."""
from copy import deepcopy
from pathlib import Path
import re
from types import SimpleNamespace

from ..resolved_project import canonical_sha256
from .animated_store import AnimatedStore
from .pipeline_run import PipelineRunError
from .storage_io import directory, read_document

PROFILE = 'joint-animation-body-source-v1'


def _related_request(value, request):
    """Registration binds the same character/motion, but may use another camera."""
    receipt = value['receipt']
    digest = receipt.get('source_request_sha256')
    if digest == canonical_sha256(request):
        return
    audit = receipt.get('pose_audit', {}).get('source_request')
    if not isinstance(audit, dict) or digest != canonical_sha256(audit):
        raise PipelineRunError('joint_animation_related_source_request_mismatch')
    if any(audit.get(key) != request.get(key) for key in ('motion_identity', 'projection', 'clip')):
        raise PipelineRunError('joint_animation_related_source_request_mismatch')


def _context(manager, job, registration):
    if registration is not None and (not isinstance(registration, str)
            or not re.fullmatch('[a-f0-9]{64}', registration)):
        raise PipelineRunError('joint_animation_registration_invalid')
    parent = manager.get(job)
    if parent.get('kind') != 'adapt' or parent.get('status') != 'succeeded':
        raise PipelineRunError('joint_animation_parent_unavailable')
    request = read_document(manager.folder(job)/'request.json')
    if request.get('joint_execution'):
        raise PipelineRunError('joint_animation_original_body_required')
    baseline = parent['result']['artifact_sha256']
    evidence = receipt = related = None
    if registration is None:
        artifact = baseline
        files = AnimatedStore(manager.state_root).read(artifact)
    else:
        from .motion_related_candidates import load
        value, files = load(manager, job, registration)
        if value['baseline_sha256'] != baseline or value['request_sha256'] != canonical_sha256(request):
            raise PipelineRunError('joint_animation_parent_changed')
        _related_request(value, request)
        related = value
        artifact = value['candidate_sha256']
        evidence, receipt = canonical_sha256(value['evidence']), canonical_sha256(value['receipt'])
    provenance = dict(profile=PROFILE, kind='related' if registration else 'main', parent_job_id=job,
        baseline_artifact_sha256=baseline, parent_request_sha256=canonical_sha256(request),
        artifact_sha256=artifact, registration_sha256=registration,
        related_evidence_sha256=evidence, related_receipt_sha256=receipt)
    assert_unchanged(manager, provenance)
    return dict(parent=deepcopy(parent), request=request, files=files, related=related,
                artifact_sha256=artifact, provenance=provenance)


def assert_unchanged(manager, provenance):
    """Cheap recheck suitable for the submission lock and after lengthy work."""
    if provenance.get('profile') != PROFILE:
        raise PipelineRunError('joint_animation_source_provenance_invalid')
    job = provenance['parent_job_id']
    parent = manager.get(job)
    request = read_document(manager.folder(job)/'request.json')
    if (parent.get('kind') != 'adapt' or parent.get('status') != 'succeeded'
            or parent['result']['artifact_sha256'] != provenance['baseline_artifact_sha256']
            or canonical_sha256(request) != provenance['parent_request_sha256']):
        raise PipelineRunError('joint_animation_parent_changed')
    registration = provenance['registration_sha256']
    if registration is not None:
        from .motion_related_candidates import _registration
        value, _ = _registration(manager, job, registration)
        if (value['candidate_sha256'] != provenance['artifact_sha256']
                or canonical_sha256(value['evidence']) != provenance['related_evidence_sha256']
                or canonical_sha256(value['receipt']) != provenance['related_receipt_sha256']):
            raise PipelineRunError('joint_animation_source_provenance_changed')
    elif provenance['artifact_sha256'] != provenance['baseline_artifact_sha256']:
        raise PipelineRunError('joint_animation_source_provenance_changed')


def source_context(manager, job, registration=None):
    """Resolve editor input; never accept an arbitrary artifact address from UI."""
    from .motion_target_jobs import assert_current
    request = read_document(manager.folder(job)/'request.json')
    assert_current(manager, request)
    result = _context(manager, job, registration)
    assert_current(manager, result['request'])
    return result


def _disk_manager(state_root):
    state_root = Path(state_root)
    def folder(job):
        if not isinstance(job, str) or not re.fullmatch('motion-[a-f0-9]{32}', job):
            raise PipelineRunError('motion_job_id_invalid')
        return directory(state_root/'jobs'/'motion-intake-v1'/job)
    return SimpleNamespace(state_root=state_root, folder=folder,
                           get=lambda job: read_document(folder(job)/'result.json'))


def frozen_context(state_root, request):
    """Worker reads full registered evidence again; queue checks live sources."""
    frozen = request['joint_execution']
    provenance = frozen.get('source_provenance')
    if provenance is not None and (not isinstance(provenance, dict) or provenance.get('profile') != PROFILE):
        raise PipelineRunError('joint_animation_source_provenance_invalid')
    manager = _disk_manager(state_root)
    result = _context(manager, frozen['parent_job_id'],
                      provenance['registration_sha256'] if provenance else None)
    if provenance is not None and result['provenance'] != provenance:
        raise PipelineRunError('joint_animation_source_provenance_changed')
    if frozen['parent_artifact_sha256'] != result['artifact_sha256']:
        raise PipelineRunError('joint_animation_parent_changed')
    # M5 copies the source request, replacing only the job id and adding controls.
    ignored = {'job_id', 'joint_execution'}
    if ({k:v for k,v in request.items() if k not in ignored}
            != {k:v for k,v in result['request'].items() if k not in ignored}):
        raise PipelineRunError('joint_animation_source_request_changed')
    return result


def assert_frozen_unchanged(state_root, request):
    """Recheck the parent/registration immediately before publishing a result."""
    frozen = request['joint_execution']
    if frozen.get('source_provenance'):
        assert_unchanged(_disk_manager(state_root), frozen['source_provenance'])
    else:
        # Preserve the historical main-source behavior for already queued jobs.
        parent = _disk_manager(state_root).get(frozen['parent_job_id'])
        if parent.get('status') != 'succeeded' or parent['result']['artifact_sha256'] != frozen['parent_artifact_sha256']:
            raise PipelineRunError('joint_animation_parent_changed')
