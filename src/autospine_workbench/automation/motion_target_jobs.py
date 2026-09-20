"""Source-bound target jobs and playback; never replace a reviewed character."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from types import SimpleNamespace
from threading import Event
from uuid import uuid4
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from ..resolved_project import canonical_sha256
from ..safe_input_files import read_real_file
from .character_capture import review_name
from .pipeline_run import PipelineRunError
from .storage_io import directory, publish_document, read_document


def assert_current(manager, request):
    source = manager.get(request['source_job_id'])
    if canonical_sha256(source) != request['source_job_sha256']:
        raise PipelineRunError('motion_target_source_changed')
    raw = read_real_file(manager.folder(source['job_id']) / ('source.' + source['format']), 64 << 20, 'motion source')
    if sha256(raw).hexdigest() != source['source_sha256']:
        raise PipelineRunError('motion_source_changed')
    characters = manager.character_manager()
    value = characters.get(request['project_id'], request['character_job_id'])
    if value.get('status') != 'needs_review' or value.get('artifact_sha256') != request['character_sha256']:
        raise PipelineRunError('motion_target_character_changed')


def submit(manager, source_job, body):
    if (set(body) - {'project_id', 'character_job_id', 'contact_correction'}
            or not {'project_id', 'character_job_id'} <= set(body)
            or type(body.get('contact_correction', True)) is not bool):
        raise PipelineRunError('motion_request_invalid')
    source = manager.get(source_job)
    if (source.get('kind', 'import') not in ('import', 'generate') or source.get('status') != 'succeeded'
            or source.get('result', {}).get('motion_status') != 'compiled'):
        raise PipelineRunError('motion_target_source_unavailable')
    characters = manager.character_manager()
    project, character_job = body['project_id'], body['character_job_id']
    characters.verified_files(project, character_job)
    character = characters.get(project, character_job)
    request = dict(kind='adapt', source_job_id=source_job, source_job_sha256=canonical_sha256(source),
                   motion_identity=source['result']['motion'], project_id=project, character_job_id=character_job,
                   character_sha256=character['artifact_sha256'], name=source['name'],
                   contact_correction=body.get('contact_correction', True))
    assert_current(manager, request)
    with manager._lock:
        if manager._closed or sum(j['status'] in {'pending', 'running'} for j in manager._jobs.values()) >= 2:
            raise PipelineRunError('motion_queue_full')
        job = 'motion-' + uuid4().hex
        root = manager.folder(job, True)
        request['job_id'] = job
        publish_document(root / 'request.json', request, staging=root / 'staging')
        value = dict(job_id=job, kind='adapt', project_id=project, character_job_id=character_job,
                     name=source['name'], status='pending', step='queued', authority='none')
        manager._jobs[job] = value
        manager._cancel[job] = Event()
        manager._pool.submit(manager._execute, job)
        return deepcopy(value)


def context(manager, job):
    value = manager.get(job)
    if value.get('kind') != 'adapt' or value['status'] != 'succeeded':
        raise PipelineRunError('motion_preview_unavailable')
    result = value['result']
    store = manager.character_manager().application.store
    files = store.read(result['artifact_sha256'])
    return result, files


def review_file(manager, job, parts):
    if (parts == ['player.html'] or len(parts) == 2 and parts[0] == 'player-assets'
            and parts[1] in ('client.js', 'style.css', 'inspection.js')):
        from .character_player import read
        # These are static application assets. Actual scene and runtime reads below
        # still verify the addressed job, character sources and capture inventory.
        return read(None, None, None, parts)
    result, files = context(manager, job)
    if parts == ['motion-contact.json']:
        return files['motion-contact.json'], 'application/json'
    if parts == ['contact.html']:
        from ..targets.character43.motion_contact_review import render
        return render(json.loads(files['motion-contact.json'])), 'text/html; charset=utf-8'
    root = directory(manager.folder(job) / 'runtime')
    def runtime_file(name):
        name = review_name(name)
        expected = result.get('runtime', {}).get('files', {}).get(name)
        if not expected:
            raise PipelineRunError('pipeline_artifact_not_found')
        directory((root / name).parent)
        raw = read_real_file(root / name, 64 << 20, 'motion runtime')
        if sha256(raw).hexdigest() != expected:
            raise PipelineRunError('pipeline_artifact_invalid')
        return raw
    if parts == ['player.html'] or parts[:1] == ['player-assets']:
        from .character_player import read
        adapter = SimpleNamespace(projects=manager.projects,
                                  review_context=lambda *_: (result, files, runtime_file('report.json')))
        return read(adapter, None, None, parts)
    name = '/'.join(parts)
    raw = runtime_file(name)
    suffix = name.rsplit('.', 1)[-1]
    return raw, {'html': 'text/html; charset=utf-8', 'json': 'application/json', 'png': 'image/png'}[suffix]


def download(manager, job):
    result, files = context(manager, job)
    output = BytesIO()
    with ZipFile(output, 'w', compression=ZIP_STORED) as archive:
        for name, raw in sorted(files.items()):
            archive.writestr(ZipInfo(name, (1980, 1, 1, 0, 0, 0)), raw)
    assert_current(manager, read_document(manager.folder(job) / 'request.json'))
    return output.getvalue()
