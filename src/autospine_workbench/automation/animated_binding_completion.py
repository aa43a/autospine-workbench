"""Explicit, reversible candidate-profile upgrade; never a binding decision."""
from ..asset.joints.binding_completion import PROFILE, build_completion, inherit_unchanged
from ..asset.joints.layer_binding import build_layer_bindings
from ..benchmark.artifacts import read_report, publish_report
from ..project_authoring_transaction import project_authoring_transaction
from ..resolved_project import canonical_sha256
from .animated_inputs import AnimatedSourceError, load_inputs, _registrations, _folder
from .animated_input_index import assert_registered_current
from .storage_io import publish_document, read_document


def rebuild_bindings(candidate, assisted, skeleton, previous):
    """Preserve the exact supported profile when downstream geometry changes."""
    if previous['profile'] == PROFILE:
        return build_completion(candidate, assisted, skeleton)
    if previous['profile'] == 'rigid-or-limb-chain-v2':
        return build_layer_bindings(candidate, assisted, skeleton)
    raise AnimatedSourceError('animated_binding_profile_unsupported')


def rebuild_from_draft(store, registration, draft, candidate, assisted, skeleton):
    previous = read_report(store.state_root, registration['manifest']['dataset_id'],
                           'layer-binding-candidates-v2', draft['source_bindings_sha256'])
    return rebuild_bindings(candidate, assisted, skeleton, previous)


def complete_bindings(store, project_id, expected_resolved_sha256, expected_input_sha256):
    try:
        with project_authoring_transaction(store.state_root, project_id):
            with load_inputs(store, project_id) as source:
                addresses = source.source_addresses
                if (addresses['input_identity_sha256'] != expected_input_sha256 or
                        addresses['resolved_project_sha256'] != expected_resolved_sha256):
                    raise AnimatedSourceError('animated_review_conflict')
                if source.bindings['profile'] == PROFILE:
                    return {'changed': False, 'added_options': 0, 'authority': 'none'}
                completed = build_completion(source.candidate, source.assisted, source.skeleton)
                draft = inherit_unchanged(source.bindings, source.draft, completed)
                added = sum(len(new['options']) - len(old['options'])
                            for old, new in zip(source.bindings['bindings'], completed['bindings']))
                for record, old in zip(draft['records'], source.draft['records']):
                    record['notes'] = old['notes']
            assert_registered_current(store, project_id, addresses)
            digest, before = _registrations(store, project_id)[-1]
            if before['revision'] >= 255:
                raise AnimatedSourceError('animated_review_history_limit')
            dataset = before['manifest']['dataset_id']
            publish_report(store.state_root, dataset, 'layer-binding-candidates-v2', completed)
            draft_sha = publish_report(store.state_root, dataset, 'layer-binding-drafts-v2', draft)
            after = dict(before, source_draft_sha256=draft_sha, revision=before['revision'] + 1,
                         previous_sha256=digest)
            folder = _folder(store, project_id)
            destination = folder / f"{after['revision']:06d}.json"
            if not publish_document(destination, after, staging=folder / 'staging'):
                raise AnimatedSourceError('animated_review_conflict')
            if read_document(destination) != after:
                raise AnimatedSourceError('animated_source_invalid')
            return {'changed': True, 'added_options': added, 'authority': 'none',
                    'bindings_sha256': canonical_sha256(completed)}
    except AnimatedSourceError:
        raise
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise AnimatedSourceError('animated_binding_completion_invalid') from exc
