"""Plan an atomic batch undo while preserving unrelated later selections."""
from copy import deepcopy
from ..benchmark.artifacts import read_report


def _compatible_upgrade(store,dataset,before_sha,current_sha,selected):
    if before_sha==current_sha:return True
    try:
        before=read_report(store.state_root,dataset,'layer-binding-candidates-v2',before_sha)
        current=read_report(store.state_root,dataset,'layer-binding-candidates-v2',current_sha)
        allowed={('rigid-or-limb-chain-v2','rigid-name-completion-v3'),
                 ('rigid-or-limb-chain-v2','rigid-detail-completion-v4'),
                 ('rigid-name-completion-v3','rigid-detail-completion-v4')}
        allowed.update((profile, 'rigid-garment-completion-v5') for profile in (
            'rigid-or-limb-chain-v2', 'rigid-name-completion-v3', 'rigid-detail-completion-v4'))
        if (before['profile'],current['profile']) not in allowed:return False
        # Candidate pixels, reviewed skeleton and all source metadata stay exact.
        strip=lambda value:{k:v for k,v in value.items() if k not in {'profile','bindings'}}
        if strip(before)!=strip(current):return False
        ids=lambda value:[r['layer_id'] for r in value['bindings']]
        if ids(before)!=ids(current) or len(ids(current))!=len(set(ids(current))):return False
        old={r['layer_id']:r for r in before['bindings'] if r['layer_id'] in selected}
        new={r['layer_id']:r for r in current['bindings'] if r['layer_id'] in selected}
        return set(old)==selected and old==new
    except (KeyError,TypeError,ValueError,OSError):
        return False


def plan_undo(store,doc,history):
    dataset=history[-1][1]['manifest']['dataset_id']
    read=lambda sha:read_report(store.state_root,dataset,'layer-binding-drafts-v2',sha)
    before=read(doc['before_draft_sha256']);after=read(doc['after_draft_sha256'])
    selected=set(doc['changed_layer_ids']);expected={r['layer_id']:r for r in after['records'] if r['layer_id'] in selected}
    index=next(i for i,(digest,_) in enumerate(history) if digest==doc['after_registration_sha256'])
    reason=None;latest=after
    for _,entry in history[index+1:]:
        latest=read(entry['source_draft_sha256'])
        if not _compatible_upgrade(store,dataset,after['source_bindings_sha256'],latest['source_bindings_sha256'],selected):
            reason='binding_source_changed';break
        actual={r['layer_id']:r for r in latest['records'] if r['layer_id'] in selected}
        if actual!=expected:
            reason='binding_batch_edited_after_adoption';break
    records=deepcopy(latest['records'])
    original={r['layer_id']:r for r in before['records']}
    if reason is None:
        records=[deepcopy(original[r['layer_id']]) if r['layer_id'] in selected else r for r in records]
    return {'can_undo':reason is None,'reason_code':reason,'records':records}
