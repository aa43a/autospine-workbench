"""Exhaust existing safe rules while keeping each committed decision reversible."""
from ..project_authoring_transaction import project_authoring_transaction
from .animated_inputs import load_inputs,AnimatedSourceError
from .pixel_head_anchor_policy import propose
from .simple_binding_adoption import apply

MAX_ROUNDS=32


def apply_all(store,project,expected_input):
    batches=[];seen=set();expected=expected_input
    def result(status,reason):
        return dict(schema='autospine.binding-auto-run/v1',authority='none',production_authorized=False,
            changed=bool(batches),status=status,reason_code=reason,batches=batches,
            changed_layer_ids=sorted(seen),rounds=len(batches))
    # Existing adoption uses the same reentrant authoring lock. Each batch remains
    # independently committed; interruption never fabricates one all-or-nothing decision.
    with project_authoring_transaction(store.state_root,project):
        for _ in range(MAX_ROUNDS):
            try:
                with load_inputs(store,project) as source:
                    if source.source_addresses['input_identity_sha256']!=expected:
                        raise AnimatedSourceError('animated_review_conflict')
                    eligible={r['layer_id'] for r in propose(source)['rows'] if r['status']=='eligible'}
                if not eligible:return result('succeeded','safe_bindings_exhausted')
                if eligible & seen:return result('stopped','binding_auto_no_progress')
                operation=apply(store,project,expected)
                if not operation['changed']:return result('stopped','binding_auto_no_progress')
                changed=operation['changed_layer_ids']
                batches.append(dict(decision_sha256=operation['decision_sha256'],changed_layer_ids=changed))
                seen.update(changed)
                if set(changed)!=eligible:return result('stopped','binding_auto_scope_changed')
                with load_inputs(store,project) as source:
                    expected=source.source_addresses['input_identity_sha256']
            except (ValueError,RuntimeError,OSError) as exc:
                if not batches:raise
                return result('stopped',getattr(exc,'reason_code','binding_auto_interrupted'))
        return result('stopped','binding_auto_round_limit')
