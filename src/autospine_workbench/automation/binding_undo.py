"""Plan an atomic batch undo while preserving unrelated later selections."""
from copy import deepcopy
from ..benchmark.artifacts import read_report


def plan_undo(store,doc,history):
    dataset=history[-1][1]['manifest']['dataset_id']
    read=lambda sha:read_report(store.state_root,dataset,'layer-binding-drafts-v2',sha)
    before=read(doc['before_draft_sha256']);after=read(doc['after_draft_sha256'])
    selected=set(doc['changed_layer_ids']);expected={r['layer_id']:r for r in after['records'] if r['layer_id'] in selected}
    index=next(i for i,(digest,_) in enumerate(history) if digest==doc['after_registration_sha256'])
    reason=None;latest=after
    for _,entry in history[index+1:]:
        latest=read(entry['source_draft_sha256'])
        if latest['source_bindings_sha256']!=after['source_bindings_sha256']:
            reason='binding_source_changed';break
        actual={r['layer_id']:r for r in latest['records'] if r['layer_id'] in selected}
        if actual!=expected:
            reason='binding_batch_edited_after_adoption';break
    records=deepcopy(latest['records'])
    original={r['layer_id']:r for r in before['records']}
    if reason is None:
        records=[deepcopy(original[r['layer_id']]) if r['layer_id'] in selected else r for r in records]
    return {'can_undo':reason is None,'reason_code':reason,'records':records}
