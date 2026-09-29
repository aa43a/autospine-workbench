"""Source-bound edit preflight receipts. Validation does not approve a candidate."""
import json
import re
from ..resolved_project import canonical_sha256
from ..targets.character43.rig_edit_operations import apply_operations, empty
from ..targets.character43.motion_layer_edits import validate
from .animated_store import AnimatedStore
from .pipeline_run import PipelineRunError
from .storage_io import directory, publish_document, read_document

PROFILE = 'autospine.rig-edit-check/v1'


def check(manager, source_job, body):
    if (set(body) != {'project_id', 'character_job_id', 'baseline', 'operations'}
            or any(not isinstance(body[key], str) or not body[key] or len(body[key]) > 200
                   for key in ('project_id', 'character_job_id'))):
        raise PipelineRunError('rig_edit_check_invalid')
    source = manager.get(source_job)
    if (source.get('status') != 'succeeded' or source.get('kind', 'import') not in ('import', 'generate')
            or source.get('result', {}).get('motion_status') != 'compiled'):
        raise PipelineRunError('motion_target_source_unavailable')
    character, _ = manager.character_manager().verified_snapshot(body['project_id'], body['character_job_id'])
    rig = json.loads(AnimatedStore(manager.state_root).read(character['artifact_sha256'])['skeleton.json'])
    result = apply_operations(body['baseline'], body['operations'], rig)
    if not result['ok']:
        return result
    receipt = dict(schema=PROFILE, source_job_id=source_job, source_job_sha256=canonical_sha256(source),
                   project_id=body['project_id'], character_job_id=body['character_job_id'],
                   character_sha256=character['artifact_sha256'],
                   baseline=validate(empty() if body['baseline'] is None else body['baseline'], rig),
                   operations=body['operations'], result=result, authority='none',
                   validation_scope='structure_and_attachment_compatibility_only')
    digest = canonical_sha256(receipt)
    root = directory(manager.folder(source_job) / 'layer-edit-checks', create=True)
    if not publish_document(root / f'{digest}.json', receipt, staging=root / 'staging'):
        if read_document(root / f'{digest}.json') != receipt:
            raise PipelineRunError('rig_edit_receipt_invalid')
    return dict(result, receipt_sha256=digest, character_sha256=character['artifact_sha256'],
                validation_scope=receipt['validation_scope'])


def read(manager, source_job, digest):
    if not isinstance(digest, str) or re.fullmatch('[a-f0-9]{64}', digest) is None:
        raise PipelineRunError('rig_edit_receipt_invalid')
    receipt = read_document(manager.folder(source_job) / 'layer-edit-checks' / f'{digest}.json')
    if canonical_sha256(receipt) != digest or receipt.get('schema') != PROFILE or receipt.get('source_job_id') != source_job:
        raise PipelineRunError('rig_edit_receipt_invalid')
    return receipt


def verify(manager, request, digest):
    receipt = read(manager, request['source_job_id'], digest)
    fields = ('source_job_id', 'source_job_sha256', 'project_id', 'character_job_id', 'character_sha256')
    if any(receipt.get(key) != request.get(key) for key in fields):
        raise PipelineRunError('rig_edit_receipt_stale')
    if receipt['result']['value'] != request.get('layer_edits', empty()):
        raise PipelineRunError('rig_edit_receipt_edits_changed')
    return receipt
