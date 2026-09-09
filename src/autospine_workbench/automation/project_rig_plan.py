"""Current-project access to the existing alpha/semantic rig planner.

Plans are read-only candidate reports. They never mutate a binding draft or
register new inputs, and cached plans are exposed only for the exact source.
"""
from pathlib import Path

from ..benchmark.artifacts import publish_report, read_report
from ..manifest_artifacts import require_safe_token, require_sha256
from ..spine42_v3_bundle_files import existing_exact_child
from .animated_input_index import inspect_registration, assert_registered_current
from .animated_inputs import AnimatedSourceError, load_inputs, _registrations
from .pipeline_run import PipelineRunError
from .storage_io import directory, publish_document, read_document


KINDS = {'rigid', 'weighted_mesh', 'partition_mesh', 'facial',
         'secondary_motion', 'semantic_review'}
# The stored v1 contract is readable without optional image-analysis dependencies.
PROFILE = 'semantic-alpha-bone-strategy-v1'


def build(*args):
    from ..asset.planning.rig_planner import build as compile_plan
    return compile_plan(*args)


def _folder(store, project_id, create=False):
    require_safe_token(project_id, 'Project id')
    return directory(Path(store.state_root) / 'project-rig-plans' / project_id, create=create)


def _status(project_id, identity, **extra):
    return dict(schema='autospine.project-rig-plan-status/v1', project_id=project_id,
                input_identity_sha256=identity, status='missing', authority='none', **extra)


def validate_sources(document, info):
    """Check exact cached identities/inventory without repeating alpha analysis."""
    addresses = info['source_addresses']
    expected = {
        'source_candidate_sha256': addresses['semantic_candidate_sha256'],
        'source_skeleton_sha256': addresses['skeleton_candidate_sha256'],
        'source_bindings_sha256': addresses['layer_bindings_sha256'],
        'source_draft_sha256': addresses['layer_binding_draft_sha256'],
    }
    ids = [row['layer_id'] for row in info['candidate']['layers']]
    if (document.get('schema') != 'autospine.rig-plan/v1' or document.get('profile') != PROFILE
            or document.get('authority') != 'none' or document.get('production_authorized') is not False
            or document.get('status') != 'needs_review'
            or any(document.get(key) != value for key, value in expected.items())
            or document.get('scope') != ids or [row['layer_id'] for row in document['layers']] != ids):
        raise AnimatedSourceError('project_rig_plan_source_mismatch')
    for row, layer, decision in zip(document['layers'], info['candidate']['layers'], info['draft']['records']):
        if (row['image_sha256'] != layer['image_sha256'] or row['name'] != layer['name']
                or row['existing_action'] != decision['action'] or row['strategy'] not in KINDS
                or row['status'] != 'needs_review' or row['confidence'] is not None):
            raise AnimatedSourceError('project_rig_plan_source_mismatch')
    return document


def read_plan(store, project_id):
    info = inspect_registration(store, project_id)
    addresses = info['source_addresses']
    identity = addresses['input_identity_sha256']
    require_sha256(identity, 'Input identity')
    result = _status(project_id, identity)
    try:
        folder = _folder(store, project_id)
    except PipelineRunError as exc:
        if exc.reason_code == 'pipeline_run_not_found':
            assert_registered_current(store, project_id, addresses)
            return result
        raise
    path = existing_exact_child(folder, f'{identity}.json')
    if path is not None:
        pointer = read_document(path)
        if (set(pointer) != {'input_identity_sha256', 'plan_sha256', 'authority'}
                or pointer['input_identity_sha256'] != identity or pointer['authority'] != 'none'):
            raise AnimatedSourceError('project_rig_plan_invalid')
        dataset = _registrations(store, project_id)[-1][1]['manifest']['dataset_id']
        plan = read_report(store.state_root, dataset, 'rig-plans-v1', pointer['plan_sha256'])
        validate_sources(plan, info)
        result.update(status='ready', plan_sha256=pointer['plan_sha256'], plan=plan)
    assert_registered_current(store, project_id, addresses)
    return result


def prepare_plan(store, project_id, expected_resolved_sha256, expected_input_sha256):
    info = inspect_registration(store, project_id)
    addresses = info['source_addresses']
    if (addresses['resolved_project_sha256'] != expected_resolved_sha256
            or addresses['input_identity_sha256'] != expected_input_sha256):
        raise AnimatedSourceError('animated_review_conflict')
    previous = read_plan(store, project_id)
    if previous['input_identity_sha256'] != expected_input_sha256:
        raise AnimatedSourceError('animated_review_conflict')
    if previous['status'] == 'ready':
        return previous
    with load_inputs(store, project_id) as source:
        if source.source_addresses != addresses:
            raise AnimatedSourceError('animated_review_conflict')
        try:
            plan = build(source.candidate, source.skeleton, source.bindings, source.draft, source.images)
        except ImportError as exc:
            raise AnimatedSourceError('project_rig_plan_dependency_missing') from exc
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise AnimatedSourceError('project_rig_plan_analysis_failed') from exc
        validate_sources(plan, info)
        source.assert_current()
        dataset = _registrations(store, project_id)[-1][1]['manifest']['dataset_id']
        digest = publish_report(store.state_root, dataset, 'rig-plans-v1', plan)
        folder = _folder(store, project_id, create=True)
        pointer = dict(input_identity_sha256=expected_input_sha256, plan_sha256=digest, authority='none')
        path = folder / f'{expected_input_sha256}.json'
        publish_document(path, pointer, staging=folder / 'staging')
        if read_document(path) != pointer:
            raise AnimatedSourceError('project_rig_plan_invalid')
    result = read_plan(store, project_id)
    if result['input_identity_sha256'] != expected_input_sha256:
        raise AnimatedSourceError('animated_review_conflict')
    return result
