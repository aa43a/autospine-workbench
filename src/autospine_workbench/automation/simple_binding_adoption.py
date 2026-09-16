"""Immutable policy evidence and CAS undo without changing historical drafts."""
from copy import deepcopy

from ..benchmark.artifacts import publish_report, read_report
from ..project_authoring_transaction import project_authoring_transaction
from ..resolved_project import canonical_sha256
from .animated_inputs import load_inputs, _registrations, save_binding_review, AnimatedSourceError
from .pixel_head_anchor_policy import propose

KIND = 'simple-binding-decisions-v1'


def apply(store, project_id, expected_input):
    with project_authoring_transaction(store.state_root,project_id):
        with load_inputs(store,project_id) as source:
            if source.source_addresses['input_identity_sha256'] != expected_input:
                raise AnimatedSourceError('animated_review_conflict')
            proposal = propose(source)
            records = deepcopy(source.draft['records'])
            changed = []
            for record,row in zip(records,proposal['rows']):
                if row['status']=='eligible':
                    record.update(action='bind',option_id=row['option_id'])
                    changed.append(record['layer_id'])
            before_draft = deepcopy(source.draft)
        if not changed:return {'changed':False,'proposal':proposal}
        before_sha,before = _registrations(store,project_id)[-1]
        after_draft = dict(before_draft,records=records)
        after = dict(before,source_draft_sha256=canonical_sha256(after_draft),
                     previous_sha256=before_sha,revision=before['revision']+1)
        decision = {'schema':'autospine.simple-binding-decision/v7','authority':'none',
                    'production_authorized':False,'decision_source':'policy_auto','project_id':project_id,
                    'proposal':proposal,'before_registration_sha256':before_sha,
                    'after_registration_sha256':canonical_sha256(after),
                    'before_draft_sha256':canonical_sha256(before_draft),
                    'after_draft_sha256':canonical_sha256(after_draft),'changed_layer_ids':changed}
        # Publish proof first. An interrupted write leaves inactive evidence, never
        # an automatic selection with no provenance. Registration is the commit point.
        digest = publish_report(store.state_root,before['manifest']['dataset_id'],KIND,decision)
        save_binding_review(store,project_id,expected_input,records)
        if _registrations(store,project_id)[-1][0]!=decision['after_registration_sha256']:
            raise AnimatedSourceError('animated_review_conflict')
        return {'changed':True,'decision_sha256':digest,'changed_layer_ids':changed,'authority':'none'}


def read_decision(store,project_id,digest):
    history = _registrations(store,project_id)
    doc = read_report(store.state_root,history[-1][1]['manifest']['dataset_id'],KIND,digest)
    if (doc.get('project_id')!=project_id or doc.get('schema') not in ('autospine.simple-binding-decision/v1','autospine.simple-binding-decision/v2','autospine.simple-binding-decision/v3','autospine.simple-binding-decision/v4','autospine.simple-binding-decision/v5','autospine.simple-binding-decision/v6','autospine.simple-binding-decision/v7')
            or doc.get('decision_source')!='policy_auto' or doc.get('production_authorized') is not False):
        raise ValueError('binding_decision_source_mismatch')
    pair=next(((old,new) for old,new in zip(history,history[1:])
               if old[0]==doc['before_registration_sha256'] and new[0]==doc['after_registration_sha256']),None)
    if pair is None or pair[0][1]['source_draft_sha256']!=doc['before_draft_sha256'] \
            or pair[1][1]['source_draft_sha256']!=doc['after_draft_sha256']:
        raise ValueError('binding_decision_not_committed')
    dataset=history[-1][1]['manifest']['dataset_id']
    before=read_report(store.state_root,dataset,'layer-binding-drafts-v2',doc['before_draft_sha256'])
    after=read_report(store.state_root,dataset,'layer-binding-drafts-v2',doc['after_draft_sha256'])
    changed=[a['layer_id'] for a,b in zip(before['records'],after['records']) if a!=b]
    if before['source_bindings_sha256']!=after['source_bindings_sha256'] or changed!=doc['changed_layer_ids']:
        raise ValueError('binding_decision_source_mismatch')
    return doc,history


def undo(store,project_id,digest,expected_input):
    with project_authoring_transaction(store.state_root,project_id):
        doc,history = read_decision(store,project_id,digest)
        from .binding_undo import plan_undo
        plan=plan_undo(store,doc,history)
        if not plan['can_undo']:
            raise AnimatedSourceError('animated_review_conflict')
        # Keep an explicit exception marker so future automatic continuation cannot
        # immediately re-adopt the selection the user just withdrew.
        for record in plan['records']:
            if record['layer_id'] in doc['changed_layer_ids']:
                record['notes']=(record['notes']+'\n用户撤销自动采用，保留人工复核。').strip()
        save_binding_review(store,project_id,expected_input,plan['records'])
        return {'changed':True,'reverted_decision_sha256':digest,'authority':'none'}
