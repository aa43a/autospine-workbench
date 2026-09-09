"""Explicitly synchronize saved authoring joint overrides into assisted inputs.

Only authored override entries are imported. Generated bbox joints, unsupported
layer changes and noncanonical joints are never silently substituted.
"""
from copy import deepcopy

from ..asset.joints.reviewed_skeleton import build_reviewed_skeleton
from ..benchmark.artifacts import read_report, publish_report
from ..benchmark.joint_draft import JOINTS
from ..project_authoring_transaction import project_authoring_transaction
from ..resolved_project import canonical_sha256
from .animated_inputs import AnimatedSourceError, _checkpoint, _registrations, _match_audit, _folder
from .animated_joint_review import _binding_draft, _validate_edit
from .storage_io import publish_document, read_document


def _source(store, project_id):
    digest, registration = _registrations(store, project_id)[-1]
    dataset = registration['manifest']['dataset_id']
    read = lambda kind, sha: read_report(store.state_root, dataset, kind, sha)
    draft = read('layer-binding-drafts-v2', registration['source_draft_sha256'])
    bindings = read('layer-binding-candidates-v2', draft['source_bindings_sha256'])
    candidate = read('semantic-candidates', bindings['candidate_sha256'])
    skeleton = read('assisted-skeleton-candidates', bindings['source_skeleton_sha256'])
    assisted = read('assisted-joint-drafts', skeleton['source_assisted_sha256'])
    if (candidate['benchmark_manifest_sha256'] != canonical_sha256(registration['manifest']) or
        skeleton['candidate_sha256'] != canonical_sha256(candidate) or
        assisted['candidate_sha256'] != canonical_sha256(candidate)):
        raise AnimatedSourceError('animated_source_invalid')
    return digest, registration, candidate, assisted, skeleton, draft


def _unsupported(store, project_id, project, candidate, registration):
    items = []
    overrides = project['overrides']
    try:
        _match_audit(store, project_id, candidate)
    except (ValueError, OSError):
        items.append({'reason_code': 'animated_rebase_audit_or_texture_changed'})
    for field, reason in [('joint_decisions', 'animated_rebase_joint_decision_unsupported'),
                          ('split_decisions', 'animated_rebase_split_unsupported')]:
        for identifier in overrides.get(field, {}):
            items.append({'id': identifier, 'reason_code': reason})
    base = store._build_project(store._record(project_id), include_overrides=False)
    layers = {row['id']: row for row in base['layers']}
    for layer, changes in overrides.get('layer_overrides', {}).items():
        for field, value in changes.items():
            if field == 'notes' or value == layers.get(layer, {}).get(field):
                continue
            reason = 'animated_rebase_split_unsupported' if field == 'split_spec' else \
                     'animated_rebase_layer_override_unsupported'
            items.append({'layer_id': layer, 'field': field, 'reason_code': reason})
    previous = registration.get('authoring_rebase', {}).get('joint_overrides', {})
    for joint in previous.keys() - overrides['joint_overrides'].keys():
        if joint in JOINTS:
            items.append({'id': joint, 'reason_code': 'animated_rebase_joint_override_removed'})
    return items


def preview_rebase(store, project_id):
    """Read-only migration plan; ready means explicit synchronization is allowed."""
    try:
        project, checkpoint = _checkpoint(store, project_id)
        digest, registration, candidate, *_ = _source(store, project_id)
        current = project['overrides']['joint_overrides']
        previous = registration.get('authoring_rebase', {}).get('joint_overrides', {})
        changed = [joint for joint in JOINTS if joint in current and
                   (joint not in previous or any(current[joint][key] != previous[joint][key] for key in ('x', 'y')))]
        unsupported = _unsupported(store, project_id, project, candidate, registration)
        return dict(status='blocked' if unsupported else 'ready',
                    expected_registration_sha256=digest,
                    expected_resolved_sha256=checkpoint['resolved_project_sha256'],
                    changed_joint_ids=changed, ignored_joint_ids=sorted(set(current) - set(JOINTS)),
                    unsupported_items=unsupported, authoring_revision=project['overrides']['revision'],
                    checkpoint_changed=checkpoint != registration['checkpoint'],
                    authority='none', production_authorized=False)
    except AnimatedSourceError:
        raise
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise AnimatedSourceError('animated_rebase_invalid') from exc


def rebase_inputs(store, project_id, expected_resolved_sha256, expected_registration_sha256):
    """CAS append a v2 registration; preserve main authoring overrides verbatim."""
    try:
        with project_authoring_transaction(store.state_root, project_id):
            plan = preview_rebase(store, project_id)
            if (plan['expected_registration_sha256'] != expected_registration_sha256 or
                plan['expected_resolved_sha256'] != expected_resolved_sha256):
                raise AnimatedSourceError('animated_review_conflict')
            if plan['status'] != 'ready':
                raise AnimatedSourceError(plan['unsupported_items'][0]['reason_code'])
            project, checkpoint = _checkpoint(store, project_id)
            digest, before, candidate, original, old_skeleton, original_draft = _source(store, project_id)
            if digest != expected_registration_sha256 or checkpoint['resolved_project_sha256'] != expected_resolved_sha256:
                raise AnimatedSourceError('animated_review_conflict')
            if not plan['checkpoint_changed']:
                return dict(input_identity_sha256=canonical_sha256(
                    {'project_checkpoint': checkpoint, 'registration_sha256': digest}), changed=False,
                    skeleton_status=old_skeleton['status'], reason_codes=old_skeleton['reason_codes'],
                    binding_review_required=False, migration_suggestions=[], imported_joint_ids=[],
                    ignored_joint_ids=plan['ignored_joint_ids'])
            if before['revision'] >= 255:
                raise AnimatedSourceError('animated_review_history_limit')
            records = deepcopy(original['draft']['records'])
            reviewed = list(original['reviewed_joint_ids'])
            current = project['overrides']['joint_overrides']
            for row in records:
                joint = row['joint_id']
                if joint in plan['changed_joint_ids']:
                    row.update(position=[current[joint]['x'], current[joint]['y']], status='observed')
                    if joint not in reviewed:
                        reviewed.append(joint)
            edited = _validate_edit(store, before, candidate, original, records, reviewed)
            skeleton = build_reviewed_skeleton(candidate, edited)
            from .animated_binding_completion import rebuild_from_draft
            bindings = rebuild_from_draft(store, before, original_draft, candidate, edited, skeleton)
            geometry_changed = (skeleton['bones'] != old_skeleton['bones'] or skeleton['status'] != old_skeleton['status'])
            draft, migrations = _binding_draft(bindings, original_draft, geometry_changed)
            dataset = before['manifest']['dataset_id']
            for kind, doc in [('assisted-joint-drafts', edited), ('assisted-skeleton-candidates', skeleton),
                              ('layer-binding-candidates-v2', bindings), ('layer-binding-drafts-v2', draft)]:
                publish_report(store.state_root, dataset, kind, doc)
            proof = dict(schema='autospine.animated-authoring-rebase/v1', authority='none',
                         annotation_mode='model_assisted', independent_annotation=False,
                         previous_registration_sha256=digest, source_checkpoint=before['checkpoint'],
                         target_checkpoint=checkpoint, authoring_revision=project['overrides']['revision'],
                         authoring_overrides_sha256=canonical_sha256(project['overrides']),
                         joint_overrides=deepcopy(current), imported_joint_ids=plan['changed_joint_ids'],
                         ignored_joint_ids=plan['ignored_joint_ids'])
            after = dict(before, schema=('autospine.animated-input-registration/v3' if before.get('source_kind') == 'project_audit'
                                         else 'autospine.animated-input-registration/v2'), checkpoint=checkpoint,
                         source_draft_sha256=canonical_sha256(draft), revision=before['revision'] + 1,
                         previous_sha256=digest, authoring_rebase=proof)
            if _checkpoint(store, project_id)[1] != checkpoint or _registrations(store, project_id)[-1][0] != digest:
                raise AnimatedSourceError('animated_review_conflict')
            folder = _folder(store, project_id)
            destination = folder / f"{after['revision']:06d}.json"
            if not publish_document(destination, after, staging=folder / 'staging'):
                raise AnimatedSourceError('animated_review_conflict')
            if read_document(destination) != after:
                raise AnimatedSourceError('animated_source_invalid')
            return dict(input_identity_sha256=canonical_sha256(
                {'project_checkpoint': checkpoint, 'registration_sha256': canonical_sha256(after)}), changed=True,
                skeleton_status=skeleton['status'], reason_codes=skeleton['reason_codes'],
                binding_review_required=bool(migrations), migration_suggestions=migrations,
                imported_joint_ids=plan['changed_joint_ids'], ignored_joint_ids=plan['ignored_joint_ids'])
    except AnimatedSourceError:
        raise
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise AnimatedSourceError('animated_rebase_invalid') from exc
