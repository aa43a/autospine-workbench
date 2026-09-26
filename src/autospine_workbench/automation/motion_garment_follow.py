"""Read-only capability and immutable scope binding for the normal repair queue."""
import json

from .pipeline_run import PipelineRunError
from .storage_io import read_document
from ..targets.character43.garment_follow_scope import resolve


def scope(manager, job, slot, animation, artifact, *, current=None):
    from .motion_target_jobs import context, assert_current
    result, files = context(manager, job) if current is None else current
    if result['artifact_sha256'] != artifact:
        raise PipelineRunError('motion_garment_candidate_changed')
    request = read_document(manager.folder(job)/'request.json')
    from .motion_corrective_parent import PROFILES
    parent = request.get('repair_execution')
    if parent and (parent.get('profile') not in PROFILES or parent['draft']['slot'] == slot):
        raise PipelineRunError('motion_repair_nested_execution_unsupported')
    assert_current(manager, request)
    character = manager.character_manager().application.store.read(request['character_sha256'])
    try:
        value = resolve(files, character, slot, animation, stable_sampling=parent is not None)
    except ValueError as error:
        raise PipelineRunError(str(error)) from error
    return dict(value, character_sha256=request['character_sha256'])


def read(manager, job, parts, result, files):
    if len(parts) != 3 or not parts[2].endswith('.json'):
        raise PipelineRunError('pipeline_artifact_not_found')
    slot, animation = parts[1], parts[2][:-5]
    value = dict(artifact_sha256=result['artifact_sha256'], slot=slot, animation=animation,
                 available=False, authority='none', selected=False)
    try:
        value['scope'] = scope(manager, job, slot, animation, result['artifact_sha256'], current=(result, files))
        value['available'] = True
    except PipelineRunError as error:
        value['reason_code'] = str(error)
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode(), 'application/json'
