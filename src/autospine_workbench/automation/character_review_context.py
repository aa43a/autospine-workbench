"""One request-scoped verified snapshot, with source checks before and after reading."""
from hashlib import sha256
import json

from ..resolved_project import canonical_sha256
from ..safe_input_files import read_real_file
from .storage_io import read_document, directory
from .pipeline_run import PipelineRunError


def load(manager, project, job):
    result = manager.get(project, job)
    if result['status'] != 'needs_review': raise PipelineRunError('pipeline_preview_not_ready')
    files = manager.application.store.read(result['artifact_sha256'])
    request = read_document(manager._path(job)/'request.json')
    sources = json.loads(files['character-manifest.json'])['source_addresses']
    if (sources['resolved_project_sha256'] != request['expected_resolved_sha256']
            or sources['input_identity_sha256'] != request['expected_input_sha256']
            or (request['sleeve_job_id'] is not None and sources.get('sleeve_job_sha256') !=
                canonical_sha256(manager.sleeves.get(project, request['sleeve_job_id'])))
            or (request['sleeve_job_id'] is None and sources.get('route_choice_sha256') != request['route_choice_sha256'])):
        raise PipelineRunError('character_artifact_source_mismatch')
    root = directory(manager._path(job)/'runtime')
    raw = read_real_file(root/'report.json', 64 << 20, 'character runtime report')
    if sha256(raw).hexdigest() != result.get('runtime', {}).get('files', {}).get('report.json'):
        raise PipelineRunError('pipeline_artifact_invalid')
    manager._current(request)
    return result, files, raw
