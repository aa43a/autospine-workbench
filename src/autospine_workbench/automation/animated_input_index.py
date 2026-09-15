"""Fast registration inspection for scheduling, never a verified rig capability.

New compilation still requires load_inputs and its complete source replay. This
index reads addressed documents and the current authoring/raster checkpoint only.
"""
from ..benchmark.artifacts import read_report
from ..benchmark.layer_binding_draft import validate_layer_binding_draft
from ..resolved_project import canonical_sha256
from . import animated_inputs as inputs
from .animated_inputs import AnimatedSourceError


def source_addresses(checkpoint, digest, registration, candidate_sha, skeleton_sha, bindings_sha, draft_sha):
    result = dict(checkpoint, animated_registration_sha256=digest,
                  benchmark_manifest_sha256=canonical_sha256(registration['manifest']),
                  semantic_candidate_sha256=candidate_sha,
                  skeleton_candidate_sha256=skeleton_sha,
                  layer_bindings_sha256=bindings_sha,
                  layer_binding_draft_sha256=draft_sha)
    result['input_identity_sha256'] = canonical_sha256(
        {'project_checkpoint': checkpoint, 'registration_sha256': digest})
    return result


def inspect_registration(store, project_id):
    """Return source identities and review metadata; no analysis or QA grant."""
    try:
        _, checkpoint = inputs._checkpoint(store, project_id)
        digest, registration = inputs._registrations(store, project_id)[-1]
        if checkpoint != registration['checkpoint']:
            raise AnimatedSourceError('animated_source_stale')
        dataset = registration['manifest']['dataset_id']
        draft_sha = registration['source_draft_sha256']
        draft = read_report(store.state_root, dataset, 'layer-binding-drafts-v2', draft_sha)
        bindings_sha = draft['source_bindings_sha256']
        bindings = read_report(store.state_root, dataset, 'layer-binding-candidates-v2', bindings_sha)
        validate_layer_binding_draft(bindings, draft)
        candidate_sha = bindings['candidate_sha256']
        candidate = read_report(store.state_root, dataset, 'semantic-candidates', candidate_sha)
        if candidate['benchmark_manifest_sha256'] != canonical_sha256(registration['manifest']):
            raise AnimatedSourceError('animated_source_invalid')
        inputs._match_audit(store, project_id, candidate)
        addresses = source_addresses(checkpoint, digest, registration, candidate_sha,
                                     bindings['source_skeleton_sha256'], bindings_sha, draft_sha)
        skeleton = read_report(store.state_root, dataset, 'assisted-skeleton-candidates',
                               bindings['source_skeleton_sha256'])
        if skeleton.get('candidate_sha256') != candidate_sha:
            raise AnimatedSourceError('animated_source_invalid')
        assert_registered_current(store, project_id, addresses)
        return {'source_addresses': addresses, 'bindings': bindings, 'draft': draft,
                'candidate': candidate, 'registration_current': True,
                'skeleton_status': skeleton.get('status'),
                'authority': 'none', 'production_authorized': False,
                'verification': 'registration_only'}
    except AnimatedSourceError:
        raise
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise AnimatedSourceError('animated_source_invalid') from exc


def assert_registered_current(store, project_id, addresses):
    """Check previously compiled output identity without rerunning its compiler.

_checkpoint hashes the current project layer bytes as well as its resolved
authoring document; texture changes invalidate cached output automatically.
"""
    try:
        _, checkpoint = inputs._checkpoint(store, project_id)
        digest, registration = inputs._registrations(store, project_id)[-1]
        identity = canonical_sha256({'project_checkpoint': checkpoint, 'registration_sha256': digest})
        if (checkpoint != registration['checkpoint'] or
            addresses['input_identity_sha256'] != identity or
            addresses['resolved_project_sha256'] != checkpoint['resolved_project_sha256'] or
            addresses['animated_registration_sha256'] != digest or
            addresses['benchmark_manifest_sha256'] != canonical_sha256(registration['manifest']) or
            addresses['layer_binding_draft_sha256'] != registration['source_draft_sha256']):
            raise AnimatedSourceError('animated_source_stale')
    except AnimatedSourceError:
        raise
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise AnimatedSourceError('animated_source_invalid') from exc
