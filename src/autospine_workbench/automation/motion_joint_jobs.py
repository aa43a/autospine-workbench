"""Freeze M5 controls against an exact, existing body animation candidate."""
from copy import deepcopy
import json
from threading import Event
from .production_submission import child_id

from ..resolved_project import canonical_sha256
from ..targets.character43.joint_animation_config import PROFILE, controls, defaults, normalize
from .pipeline_run import PipelineRunError
from .storage_io import publish_document, read_document


def eligibility(document, files=None, *, reference_times=None):
    reasons = []
    if len(document.get('skins', [])) != 1:
        reasons.append('joint_animation_single_skin_required')
    for animation in document['animations'].values():
        if any('attachment' in channels for channels in animation.get('slots', {}).values()):
            reasons.append('joint_animation_attachment_switch_not_supported')
    sampling = None
    if reference_times is not None or files:
        from ..targets.character43.joint_sampling import preflight
        if reference_times is None:
            from ..targets.character43.numeric_reference import read
            name = next(iter(document['animations']))
            reference_times = [r['time'] for r in read(files)['animations'][name]]
        sampling = preflight(reference_times)
        if not sampling['supported']:
            reasons.append('joint_animation_sample_limit_shorten_source_clip')
    return dict(supported=not reasons, reasons=sorted(set(reasons)), sampling=sampling,
                reason='、'.join(reasons) if reasons else None)


def require_body_repair_parent(manager, job):
    if read_document(manager.folder(job)/'request.json').get('joint_execution'):
        raise PipelineRunError('joint_animation_repair_original_body_required')


def context(manager, job, registration=None):
    from .motion_joint_source import source_context
    resolved = source_context(manager, job, registration)
    parent, request, files = resolved['parent'], resolved['request'], resolved['files']
    document = json.loads(files['skeleton.json'])
    if len(document['animations']) != 1:
        raise PipelineRunError('joint_animation_single_animation_required')
    from ..targets.character43.numeric_reference import read
    from hashlib import sha256
    reference = read(files)
    name = next(iter(document['animations']))
    if reference['skeleton_sha256'] != sha256(files['skeleton.json']).hexdigest():
        raise PipelineRunError('joint_animation_reference_mismatch')
    times = [row['time'] for row in reference['animations'][name]]
    duration = times[-1]
    return parent, request, files, document, name, duration, resolved['provenance'], times


def inspect(manager, job, registration=None):
    from ..targets.character43 import joint_face, joint_secondary
    parent, request, files, document, animation, duration, provenance, times = context(manager, job, registration)
    face = joint_face.inventory(files, document)
    secondary = joint_secondary.inventory(files, document)
    from .motion_source_comparison import link
    source_link = link(manager, job, parent['result'])
    source_link['artifact_sha256'] = provenance['artifact_sha256']
    return dict(schema='autospine.joint-animation-editor/v1', profile=PROFILE,
        parent_job_id=job, artifact_sha256=provenance['artifact_sha256'], source_provenance=provenance,
        registration_sha256=registration,
        source_link=source_link,
        preview_base=f'/api/motions/{job}/view/'+(f'related-candidates/{registration}/' if registration else '')+'player-assets/',
        project_id=request['project_id'], character_job_id=request['character_job_id'],
        animation=animation, duration=duration, inventory=dict(face=face, **secondary),
        eligibility=eligibility(document, reference_times=times),
        defaults=defaults(), controls=controls(), authority='none', production_authorized=False,
        limitations=['small_facial_parameters_not_new_view_art',
                     'baked_secondary_motion_not_live_runtime_physics',
                     'body_acceptance_does_not_accept_joint_animation'])


def submit(manager, job, body):
    if (not isinstance(body, dict) or set(body)-{'artifact_sha256', 'config', 'registration_sha256'}
            or not {'artifact_sha256', 'config'} <= set(body)):
        raise PipelineRunError('joint_animation_request_invalid')
    parent, request, files, document, animation, duration, provenance, times = context(manager, job, body.get('registration_sha256'))
    if body['artifact_sha256'] != provenance['artifact_sha256']:
        raise PipelineRunError('joint_animation_body_changed')
    if not eligibility(document, reference_times=times)['supported']:
        raise PipelineRunError('joint_animation_body_unsupported')
    try:
        config = normalize(body['config'], duration)
    except (ValueError, TypeError, KeyError) as exc:
        raise PipelineRunError('joint_animation_config_invalid') from exc
    with manager._lock:
        from .motion_joint_source import assert_unchanged
        assert_unchanged(manager, provenance)
        if manager._closed or sum(j['status'] in {'pending', 'running'} for j in manager._jobs.values()) >= 2:
            raise PipelineRunError('motion_queue_full')
        next_job = child_id('motion-')
        folder = manager.folder(next_job, True)
        frozen = deepcopy(request)
        frozen.update(job_id=next_job, joint_execution=dict(profile=PROFILE, parent_job_id=job,
            parent_artifact_sha256=body['artifact_sha256'], animation=animation,
            config=config, config_sha256=canonical_sha256(config), duration=duration, source_provenance=provenance))
        publish_document(folder/'request.json', frozen, staging=folder/'staging')
        row = dict(job_id=next_job, kind='adapt', project_id=request['project_id'],
            character_job_id=request['character_job_id'], name=request['name']+' · 联合动画',
            status='pending', step='queued', authority='none', joint_parent_job_id=job)
        manager._jobs[next_job] = row
        manager._cancel[next_job] = Event()
        manager._pool.submit(manager._execute, next_job)
    return deepcopy(row)


def retry(manager, request):
    execution = request['joint_execution']
    body = dict(artifact_sha256=execution['parent_artifact_sha256'], config=execution['config'])
    registration = execution.get('source_provenance', {}).get('registration_sha256')
    if registration: body['registration_sha256'] = registration
    return submit(manager, execution['parent_job_id'], body)
