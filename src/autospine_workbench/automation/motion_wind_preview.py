"""Bounded, source-checked draft computation; no jobs, publication or QA writes."""
from hashlib import sha256
import re
from types import SimpleNamespace

from ..resolved_project import canonical_sha256
from ..safe_input_files import read_real_file, strict_json_object
from ..targets.character43.joint_animation_config import PROFILE, normalize
from ..targets.character43.joint_wind_preview import compute, validate_template
from ._animated_read_cohort import prepare
from .animated_store import MAX_FILE, MAX_TOTAL
from .motion_joint_source import assert_unchanged
from .pipeline_run import PipelineRunError
from .storage_io import canonical_bytes, directory, read_document

REQUEST_SCHEMA = 'autospine.wind-preview-request/v1'
RESULT_SCHEMA = 'autospine.wind-preview-result/v1'
HASHES = ('artifact_sha256', 'skeleton_sha256', 'parent_skeleton_sha256', 'config_sha256', 'wind_preview_sha256')
FILES = ('skeleton.json', 'joint-animation.json', 'wind-preview.json')
RESPONSE_LIMIT = 8 << 20


def _invalid(reason):
    raise PipelineRunError(reason)


def _request(body):
    required = {'schema', *HASHES, 'config', 'no_wind'}
    if (not isinstance(body, dict) or not required <= set(body) or set(body)-required-{'request_id'}
            or body['schema'] != REQUEST_SCHEMA or type(body['no_wind']) is not bool
            or any(not isinstance(body[k], str) or not re.fullmatch('[a-f0-9]{64}', body[k]) for k in HASHES)
            or ('request_id' in body and (type(body['request_id']) is not int or not 0 <= body['request_id'] <= 9007199254740991))):
        _invalid('wind_preview_request_invalid')


def _bound(manager, job, body):
    # A draft acts on the frozen candidate. Current authoring-tree verification
    # belongs to a new build, not each slider movement on this immutable mesh.
    journal = SimpleNamespace(folder=manager.folder,
        get=lambda identifier: read_document(manager.folder(identifier)/'result.json'))
    value = journal.get(job)
    if value.get('kind') != 'adapt' or value.get('status') != 'succeeded':
        _invalid('wind_preview_candidate_unavailable')
    result = value['result']
    request = read_document(manager.folder(job)/'request.json')
    frozen = request.get('joint_execution')
    if (not isinstance(frozen, dict) or frozen.get('profile') != PROFILE
            or result.get('joint_animation_profile') != PROFILE):
        _invalid('wind_preview_joint_candidate_required')
    if (result.get('artifact_sha256') != body['artifact_sha256']
            or result.get('joint_config_sha256') != body['config_sha256']
            or frozen.get('config_sha256') != body['config_sha256']
            or canonical_sha256(frozen['config']) != body['config_sha256']
            or result.get('joint_parent_job_id') != frozen.get('parent_job_id')
            or result.get('joint_parent_artifact_sha256') != frozen.get('parent_artifact_sha256')
            or result.get('joint_source_provenance') != frozen.get('source_provenance')):
        _invalid('wind_preview_source_mismatch')
    provenance = frozen.get('source_provenance')
    if not provenance or provenance.get('parent_job_id') != frozen['parent_job_id'] or provenance.get('artifact_sha256') != frozen['parent_artifact_sha256']:
        _invalid('wind_preview_source_mismatch')
    assert_unchanged(journal, provenance)
    source = journal.get(request['source_job_id'])
    source_request = read_document(manager.folder(request['source_job_id'])/'request.json')
    if (canonical_sha256(source) != request['source_job_sha256']
            or source.get('job_id') != request['source_job_id'] or source.get('status') != 'succeeded'
            or source.get('kind', 'import') not in ('import', 'generate')
            or not isinstance(source.get('format'), str) or not re.fullmatch('[a-z0-9]{1,16}', source['format'])):
        _invalid('wind_preview_source_mismatch')
    raw_source = read_real_file(manager.folder(source['job_id'])/('source.'+source['format']), 64 << 20, 'wind preview source')
    if sha256(raw_source).hexdigest() != source['source_sha256']:
        _invalid('wind_preview_source_mismatch')
    character_folder = manager.character_manager()._path(request['character_job_id'])
    character_request = read_document(character_folder/'request.json')
    character = read_document(character_folder/'result.json')
    if (character_request.get('project_id') != request['project_id']
            or character.get('project_id') != request['project_id']
            or character.get('job_id') != request['character_job_id']
            or character.get('status') != 'needs_review'
            or character.get('artifact_sha256') != request['character_sha256']):
        _invalid('wind_preview_source_mismatch')
    return result, request, tuple(map(canonical_sha256, (value, request, source_request, source, character_request, character)))


def _read_candidate(store, digest):
    folder = directory(store.root/digest)
    plan = prepare(folder, digest, MAX_FILE, MAX_TOTAL)
    if not set(FILES) <= set(plan.inventory):
        _invalid('wind_preview_template_unavailable')
    files = {}
    for name in FILES:
        raw = read_real_file(folder/name, MAX_FILE, 'wind preview candidate')
        if sha256(raw).hexdigest() != plan.inventory[name]:
            _invalid('pipeline_artifact_invalid')
        files[name] = raw
    return folder, plan, files


def preview(manager, job, body):
    _request(body)
    if not isinstance(job, str) or not re.fullmatch('motion-[a-f0-9]{32}', job):
        _invalid('motion_job_id_invalid')
    result, request, identity = _bound(manager, job, body)
    store = manager.character_manager().application.store
    folder, plan, files = _read_candidate(store, body['artifact_sha256'])
    try:
        document, report, template = [strict_json_object(files[n], 'wind preview') for n in FILES]
        frozen = request['joint_execution']
        if (report.get('schema') != 'autospine.joint-animation/v1' or report.get('profile') != PROFILE
                or report.get('config') != frozen['config'] or report.get('animation') != frozen['animation']
                or report.get('duration') != frozen['duration']
                or any(report.get(k) != body[k] for k in ('skeleton_sha256', 'parent_skeleton_sha256', 'config_sha256'))
                or sha256(files['skeleton.json']).hexdigest() != body['skeleton_sha256']
                or report.get('secondary', {}).get('wind_preview') != dict(file='wind-preview.json', sha256=body['wind_preview_sha256'])
                or sha256(files['wind-preview.json']).hexdigest() != body['wind_preview_sha256']):
            _invalid('wind_preview_source_mismatch')
        parent = store.read_file(result['joint_parent_artifact_sha256'], 'skeleton.json')
        if sha256(parent).hexdigest() != body['parent_skeleton_sha256']:
            _invalid('wind_preview_source_mismatch')
        validate_template(template, report, document)
        config = normalize(body['config'], report['duration'])
        if 'wind' not in config:
            _invalid('wind_preview_config_invalid')
        for kind in ('hair', 'cloth', 'objects'):
            slots = {r['slot'] for r in report['inventory'].get(kind, [])}
            if set(config[kind]['slots'])-slots or set(config[kind]['overrides'])-slots:
                _invalid('wind_preview_config_invalid')
        computed = compute(template, report, config, no_wind=body['no_wind'])
    except PipelineRunError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        reason = str(exc) if str(exc).startswith('wind_preview_') else 'wind_preview_config_invalid'
        raise PipelineRunError(reason) from exc
    # Validate the entire inventory/tree again, including untouched file identities.
    # Only the three inputs need byte reads; textures cannot affect this calculation.
    current = prepare(folder, body['artifact_sha256'], MAX_FILE, MAX_TOTAL)
    if current != plan or _bound(manager, job, body)[2] != identity:
        _invalid('wind_preview_source_changed')
    if sha256(store.read_file(result['joint_parent_artifact_sha256'], 'skeleton.json')).hexdigest() != body['parent_skeleton_sha256']:
        _invalid('wind_preview_source_changed')
    response = dict(schema=RESULT_SCHEMA, job_id=job, **{k:body[k] for k in HASHES},
        preview_config_sha256=canonical_sha256(config), animation=report['animation'], duration=report['duration'],
        **computed, basis='frozen_candidate', authority='none', validated=False, production_authorized=False)
    response['pending'].insert(0, '基于已构建角色；修改骨架或区域归属后需重建')
    if 'request_id' in body: response['request_id'] = body['request_id']
    if len(canonical_bytes(response)) > RESPONSE_LIMIT:
        _invalid('wind_preview_response_limit')
    return response
