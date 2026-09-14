"""Explicit region repair with bounded refinement; failed trials keep the input candidate."""
import json

from .character_build_options import valid_regions
from .pipeline_run import PipelineRunError


def validate(regions):
    if regions is not None and not valid_regions(regions):
        raise PipelineRunError('shoulder_region_selection_invalid')


def apply_selected(manager, request, result, *, progress=lambda stage: None,
                   cancel_requested=lambda: False):
    try:
        return _apply(manager, request, result, progress=progress, cancel_requested=cancel_requested)
    except ValueError as exc:
        reason = str(exc)
        recoverable = {'shoulder_boundary_contact_missing', 'shoulder_boundary_support_insufficient',
                       'shoulder_boundary_free_region_missing', 'shoulder_reviewed_torso_missing',
                       'shoulder_torso_parent_unsupported', 'shoulder_adaptive_sample_budget',
                       'shoulder_temporal_sample_budget'}
        if reason not in recoverable:
            raise
        return dict(result, shoulder_trial=dict(region_ids=list(request['shoulder_regions']),
            source_artifact_sha256=result['artifact_sha256'], status='blocked', reason_code=reason,
            included_in_candidate=False, authority='none', selected=False,
            visual_contact_status='not_evaluated'))


def _apply(manager, request, result, *, progress, cancel_requested):
    regions = request.get('shoulder_regions')
    validate(regions)
    if regions is None:
        return result
    from ..targets.character43.shoulder_boundary_candidate import generate as boundary
    from ..targets.character43.shoulder_boundary_adaptive import generate as adaptive
    from ..targets.character43.shoulder_temporal import generate as temporal
    store = manager.application.store
    source = result['artifact_sha256']; files = store.read(source)
    attempts = []; stage = 'shoulder-boundary'

    def tick(_message=''):
        if cancel_requested():
            raise PipelineRunError('character_build_canceled')
        progress(stage)

    def save(output, report):
        tick()
        digest = store.publish(output)
        attempts.append(dict(artifact_sha256=digest, profile=report['profile'], status=report['status']))
        return digest

    tick()
    output, report = boundary(files, source, slot_ids=regions, progress=tick)
    digest = save(output, report)
    if report['status'] == 'blocked':
        stage = 'shoulder-adaptive'; tick()
        output, report = adaptive(files, source, output, digest, progress=tick)
        digest = save(output, report)
    if report['status'] == 'blocked':
        stage = 'shoulder-temporal'; tick()
        try:
            output, report = temporal(files, source, output, digest, progress=tick)
        except ValueError as exc:
            if str(exc) != 'shoulder_temporal_no_failing_clips':
                raise
        else:
            digest = save(output, report)
    tick()
    passed = report['status'] == 'needs_review' and report['geometry_passed']
    trial = dict(region_ids=list(regions), source_artifact_sha256=source,
                 candidate_artifact_sha256=digest, attempts=attempts,
                 status='needs_review' if passed else 'blocked', included_in_candidate=passed,
                 reason_code=None if passed else 'shoulder_geometry_blocked',
                 geometry_passed=report['geometry_passed'], dense_boundary=report['dense_boundary'],
                 authority='none', selected=False, visual_contact_status='not_evaluated')
    if not passed:
        return dict(result, shoulder_trial=trial)
    return dict(result, artifact_sha256=digest,
                manifest=json.loads(output['character-manifest.json']), shoulder_trial=trial)
