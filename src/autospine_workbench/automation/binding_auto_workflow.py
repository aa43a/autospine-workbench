"""Prepare missing candidate options before the existing bounded adoption loop."""
from ..project_authoring_transaction import project_authoring_transaction
from .animated_inputs import load_inputs, AnimatedSourceError
from .animated_binding_completion import complete_bindings
from .binding_auto_run import apply_all


def prepare_and_apply(store, project, expected_resolved, expected_input):
    with project_authoring_transaction(store.state_root, project):
        preparation = complete_bindings(store, project, expected_resolved, expected_input)
        try:
            with load_inputs(store, project) as source:
                addresses = source.source_addresses
                if addresses['resolved_project_sha256'] != expected_resolved:
                    raise AnimatedSourceError('animated_review_conflict')
                current = addresses['input_identity_sha256']
            result = apply_all(store, project, current)
        except (ValueError, RuntimeError, OSError) as exc:
            if not preparation['changed']:
                raise
            result = dict(authority='none', production_authorized=False, changed=False,
                          status='stopped', reason_code=getattr(exc, 'reason_code', 'binding_auto_interrupted'),
                          batches=[], changed_layer_ids=[], rounds=0)
        return dict(result, schema='autospine.binding-auto-workflow/v1',
                    changed=bool(preparation['changed'] or result['changed']),
                    candidate_preparation=preparation)
