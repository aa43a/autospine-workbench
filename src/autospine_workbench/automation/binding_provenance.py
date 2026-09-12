"""Read decision lineage without labelling automatic choices as human review."""
from copy import deepcopy
from hashlib import sha256
import json

from ..benchmark.artifacts import _folder,read_report
from ..resolved_project import canonical_sha256
from .animated_inputs import _registrations
from .animated_input_index import inspect_registration,assert_registered_current
from .simple_binding_adoption import read_decision,KIND
from .storage_io import canonical_bytes


def read_provenance(store,project,addresses):
    info=inspect_registration(store,project)
    if info['source_addresses']!=addresses:raise ValueError('binding_provenance_source_changed')
    history=_registrations(store,project);dataset=history[-1][1]['manifest']['dataset_id']
    decisions={}
    try:folder=_folder(store.state_root,dataset,KIND)
    except ValueError:folder=None
    if folder:
        for path in sorted(folder.glob('*.json')):
            try:doc,_=read_decision(store,project,path.stem)
            except ValueError:continue
            decisions[doc['after_registration_sha256']]=(path.stem,doc)
    previous={};lineage={}
    for index,(digest,entry) in enumerate(history):
        draft=read_report(store.state_root,dataset,'layer-binding-drafts-v2',entry['source_draft_sha256'])
        proof=decisions.get(digest)
        for record in draft['records']:
            key=record['layer_id']
            if record!=previous.get(key):
                lineage[key]={'decision_source':'legacy_selection' if index==0 else 'explicit_selection',
                              'decision_sha256':None,'policy_id':None,'evidence_current':None}
                if proof and key in proof[1]['changed_layer_ids']:
                    lineage[key]={'decision_source':'policy_auto','decision_sha256':proof[0],
                                  'policy_id':proof[1]['proposal'].get('policy_id'),
                                  'evidence_current':proof[1]['proposal']['source_addresses']['layer_bindings_sha256']==addresses['layer_bindings_sha256']}
            previous[key]=record
    rows=[]
    for record in info['draft']['records']:
        row=dict(lineage[record['layer_id']],layer_id=record['layer_id'],action=record['action'],option_id=record['option_id'])
        if row['decision_source']=='policy_auto':
            proof=next(doc for sha,doc in decisions.values() if sha==row['decision_sha256'])
            row['evidence_current']=proof['proposal']['source_addresses']['layer_bindings_sha256']==addresses['layer_bindings_sha256']
        if record['action']=='pending' and not record['notes'].strip():row['decision_source']='pending'
        rows.append(row)
    assert_registered_current(store,project,addresses)
    document={'schema':'autospine.binding-provenance/v1','authority':'none','production_authorized':False,
              'source_addresses':deepcopy(addresses),'rows':rows}
    if any(r['decision_source']=='policy_auto' and r['evidence_current'] is not True for r in rows):
        from .animated_inputs import load_inputs
        from .binding_revalidation import revalidate
        with load_inputs(store,project) as source:
            if source.source_addresses!=addresses:raise ValueError('binding_provenance_source_changed')
            validation=revalidate(source,rows)
            source.assert_current()
        passed={r['layer_id'] for r in validation['rows'] if r['passed']}
        for row in rows:
            if row['layer_id'] in passed:row['evidence_current']=True
        document.update(schema='autospine.binding-provenance/v2',revalidation=validation)
    assert_registered_current(store,project,addresses)
    return document


def attach_provenance(files,store,project,addresses):
    result=dict(files);document=read_provenance(store,project,addresses)
    raw=canonical_bytes(document);result['binding-provenance.json']=raw
    manifest=json.loads(result['character-manifest.json'])
    manifest['files']['binding-provenance.json']=sha256(raw).hexdigest()
    provenance={r['layer_id']:r for r in document['rows']}
    if set(provenance)!={r['layer_id'] for r in manifest['layers']}:
        raise ValueError('binding_provenance_inventory_mismatch')
    for row in manifest['layers']:row['binding_decision']=provenance[row['layer_id']]
    manifest['binding_provenance_sha256']=canonical_sha256(document)
    result['character-manifest.json']=canonical_bytes(manifest)
    return result
