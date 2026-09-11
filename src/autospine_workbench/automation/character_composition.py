"""Compose current character sources with an explicit, non-withdrawn sleeve job."""
from io import BytesIO
import json
from zipfile import ZipFile
from types import SimpleNamespace

from ..benchmark.artifacts import read_report
from ..resolved_project import canonical_sha256
from ..targets.character43.sleeve_package import compose_package
from .animated_input_index import inspect_registration, assert_registered_current
from .animated_jobs import safe_file
from .pipeline_run import PipelineRunError
from .storage_io import read_document


def build_character(application, sleeves, project_id, sleeve_job_id, *, progress=lambda value: None, cancel_requested=lambda: False):
    def check(stage):
        if cancel_requested():
            raise PipelineRunError('character_build_canceled')
        progress(stage)
    check('resolve')
    info = inspect_registration(application.projects, project_id)
    request = read_document(sleeves._path(sleeve_job_id) / 'request.json')
    if request['project_id'] != project_id:
        raise PipelineRunError('pipeline_job_not_found')
    sleeves._assert_current(request)
    job = sleeves.get(project_id, sleeve_job_id)
    if job['status'] != 'needs_review':
        raise PipelineRunError('pipeline_preview_not_ready')
    records = job['result']['records']; components = []; zip_addresses = []
    for index, row in enumerate(records):
        if row['status'] != 'candidate_exported':
            continue
        raw = sleeves.download(project_id, sleeve_job_id, index)
        from hashlib import sha256
        zip_addresses.append(sha256(raw).hexdigest())
        with ZipFile(BytesIO(raw)) as archive:
            if len(archive.infolist()) != 3 or len(set(archive.namelist())) != 3 \
                    or sum(item.file_size for item in archive.infolist()) > 64 << 20:
                raise PipelineRunError('character_component_zip_invalid')
            files = {safe_file(name): archive.read(name) for name in archive.namelist()}
        components.append(dict(source_layer_id=row['layer_id'], files=files))
    if not components:
        raise PipelineRunError('character_no_exportable_sleeves')
    check('base-preview')
    run = application.preview(project_id, info['source_addresses']['resolved_project_sha256'], 'limb-flex-15', cancel_requested=cancel_requested)
    check('compose')
    base = application.verified_files(project_id, run)
    scope = json.loads(base['preview-manifest.json'])
    if scope['source_addresses'] != info['source_addresses']:
        raise PipelineRunError('animated_input_changed')
    registration = application.projects.state_root
    # The exact dataset ID is carried by the source candidate, not inferred from project names.
    from . import animated_inputs
    _, registered = animated_inputs._registrations(application.projects, project_id)[-1]
    skeleton = read_report(registration, registered['manifest']['dataset_id'], 'assisted-skeleton-candidates',
                           info['source_addresses']['skeleton_candidate_sha256'])
    addresses = dict(info['source_addresses'], base_bundle_sha256=run['steps'][2]['outputs']['bundle_sha256'],
                     sleeve_job_sha256=canonical_sha256(job), sleeve_zip_inventory_sha256=canonical_sha256(zip_addresses))
    from .character_coverage_reader import read_job_coverage
    manager = SimpleNamespace(application=application, files=lambda *_: base, get=lambda *_: {'run':run})
    coverage = read_job_coverage(manager, project_id, 'exact-run')['document']
    files = compose_package(base, components, info['candidate'], skeleton, addresses, coverage, checkpoint=lambda: check('compose'))
    assert_registered_current(application.projects, project_id, info['source_addresses'])
    sleeves._assert_current(request)
    if sleeves.get(project_id, sleeve_job_id) != job:
        raise PipelineRunError('character_sleeve_job_changed')
    check('publish')
    artifact = application.store.publish(files)
    verified = application.store.read(artifact)
    if verified != files:
        raise PipelineRunError('pipeline_artifact_invalid')
    return dict(artifact_sha256=artifact, manifest=json.loads(verified['character-manifest.json']))
