"""Explicit model-assisted joint edits for registered animation candidates.

The raw pose and independent benchmark ground truth remain untouched. New joint
geometry invalidates existing binding selections, even when bone names survive.
"""
from copy import deepcopy
from urllib.parse import quote

from ..asset.joints.layer_binding import build_layer_bindings
from ..asset.joints.reviewed_skeleton import build_reviewed_skeleton
from ..benchmark.artifacts import read_report, publish_report
from ..benchmark.assisted_joint_draft import validate_assisted_joint_draft
from ..benchmark.joint_baseline import validate_joint_baseline
from ..benchmark.joint_draft import JOINTS, validate_joint_draft
from ..benchmark.layer_binding_draft import build_layer_binding_draft, validate_layer_binding_draft
from ..benchmark.pose_source import read_pose
from ..project_authoring_transaction import project_authoring_transaction
from ..resolved_project import canonical_sha256
from .animated_input_index import inspect_registration, assert_registered_current
from .animated_inputs import AnimatedSourceError, _registrations, _folder
from .storage_io import publish_document, read_document


def _source(store, project_id):
    index = inspect_registration(store, project_id)
    _, registration = _registrations(store, project_id)[-1]
    dataset = registration['manifest']['dataset_id']
    addresses = index['source_addresses']
    skeleton = read_report(store.state_root, dataset, 'assisted-skeleton-candidates',
                           addresses['skeleton_candidate_sha256'])
    assisted = read_report(store.state_root, dataset, 'assisted-joint-drafts',
                           skeleton['source_assisted_sha256'])
    if (assisted['candidate_sha256'] != addresses['semantic_candidate_sha256'] or
        assisted['annotation_mode'] != 'model_assisted' or assisted['independent_annotation'] is not False or
        skeleton['candidate_sha256'] != addresses['semantic_candidate_sha256']):
        raise AnimatedSourceError('animated_joint_source_invalid')
    validate_joint_draft(index['candidate'], assisted['draft'])
    reviewed = assisted['reviewed_joint_ids']
    if (type(reviewed) is not list or any(type(v) is not str or v not in JOINTS for v in reviewed)
        or len(set(reviewed)) != len(reviewed)):
        raise AnimatedSourceError('animated_joint_source_invalid')
    assert_registered_current(store, project_id, addresses)
    return index, registration, skeleton, assisted


def get_joint_review(store, project_id):
    """Read all 17 original assisted records without manufacturing reviews."""
    try:
        index, _, skeleton, assisted = _source(store, project_id)
        return dict(input_identity_sha256=index['source_addresses']['input_identity_sha256'],
                    records=deepcopy(assisted['draft']['records']),
                    reviewed_joint_ids=list(assisted['reviewed_joint_ids']),
                    canvas=list(index['candidate']['canvas']),
                    composite_url=f'/api/projects/{quote(project_id, safe="")}/composite',
                    annotation_mode='model_assisted', independent_annotation=False,
                    authority='none', production_authorized=False,
                    skeleton_status=skeleton['status'], reason_codes=list(skeleton['reason_codes']))
    except AnimatedSourceError:
        raise
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise AnimatedSourceError('animated_joint_source_invalid') from exc


def _validate_edit(store, registration, candidate, original, records, reviewed):
    dataset = registration['manifest']['dataset_id']
    baseline = read_report(store.state_root, dataset, 'joint-baselines', original['source_baseline_sha256'])
    audit = read_report(store.state_root, dataset, 'semantic-audits', candidate['audit_envelope_sha256'])['payload']
    validate_joint_baseline(candidate, audit, baseline)
    pose = read_pose(store.state_root, candidate, original['source_pose_sha256'])
    # Only these two explicitly submitted fields are mutable.
    edited = deepcopy(original)
    edited['draft']['records'] = deepcopy(records)
    edited['reviewed_joint_ids'] = deepcopy(reviewed)
    return validate_assisted_joint_draft(candidate, baseline, pose, edited)


def _binding_draft(bindings, original, geometry_changed):
    draft = build_layer_binding_draft(bindings)
    migrations = []
    for target, previous in zip(draft['records'], original['records']):
        if geometry_changed and previous['action'] == 'bind':
            migrations.append(dict(layer_id=previous['layer_id'], previous_option_id=previous['option_id'],
                                   reason_code='joint_geometry_changed_binding_review_required'))
        else:
            target.update(deepcopy(previous))
    return validate_layer_binding_draft(bindings, draft), migrations


def save_joint_review(store, project_id, expected_input_sha256, records, reviewed_joint_ids):
    """CAS append explicit joint edits, rebuilding downstream candidate contracts."""
    try:
        with project_authoring_transaction(store.state_root, project_id):
            index, before, old_skeleton, original = _source(store, project_id)
            addresses = index['source_addresses']
            if addresses['input_identity_sha256'] != expected_input_sha256:
                raise AnimatedSourceError('animated_review_conflict')
            candidate = index['candidate']
            edited = _validate_edit(store, before, candidate, original, records, reviewed_joint_ids)
            if edited == original:
                return dict(input_identity_sha256=expected_input_sha256, changed=False,
                            skeleton_status=old_skeleton['status'], reason_codes=old_skeleton['reason_codes'],
                            binding_review_required=False, migration_suggestions=[])
            if before['revision'] >= 255:
                raise AnimatedSourceError('animated_review_history_limit')
            skeleton = build_reviewed_skeleton(candidate, edited)
            bindings = build_layer_bindings(candidate, edited, skeleton)
            geometry_changed = (skeleton['bones'] != old_skeleton['bones'] or
                                skeleton['status'] != old_skeleton['status'])
            draft, migrations = _binding_draft(bindings, index['draft'], geometry_changed)
            dataset = before['manifest']['dataset_id']
            for kind, doc in [('assisted-joint-drafts', edited), ('assisted-skeleton-candidates', skeleton),
                              ('layer-binding-candidates-v2', bindings), ('layer-binding-drafts-v2', draft)]:
                publish_report(store.state_root, dataset, kind, doc)
            assert_registered_current(store, project_id, addresses)
            after = dict(before, source_draft_sha256=canonical_sha256(draft),
                         revision=before['revision'] + 1,
                         previous_sha256=addresses['animated_registration_sha256'])
            folder = _folder(store, project_id)
            destination = folder / f"{after['revision']:06d}.json"
            if not publish_document(destination, after, staging=folder / 'staging'):
                raise AnimatedSourceError('animated_review_conflict')
            if read_document(destination) != after:
                raise AnimatedSourceError('animated_source_invalid')
            identity = canonical_sha256({'project_checkpoint': after['checkpoint'],
                                         'registration_sha256': canonical_sha256(after)})
            return dict(input_identity_sha256=identity, changed=True,
                        skeleton_status=skeleton['status'], reason_codes=skeleton['reason_codes'],
                        binding_review_required=bool(migrations), migration_suggestions=migrations)
    except AnimatedSourceError:
        raise
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise AnimatedSourceError('animated_joint_review_invalid') from exc
