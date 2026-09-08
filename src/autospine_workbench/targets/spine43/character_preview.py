"""Compose explicitly selected rigid regions with validated corrective meshes."""
from ...resolved_project import canonical_sha256
from ...benchmark.layer_binding_draft import validate_layer_binding_draft
from .elbow_preview import build_preview


def build_character(mesh,skeleton,bake,candidate,bindings,draft):
    validate_layer_binding_draft(bindings,draft)
    if (canonical_sha256(draft)!=mesh['source_draft_sha256'] or
        canonical_sha256(bindings)!=mesh['source_bindings_sha256'] or
        canonical_sha256(skeleton)!=bindings['source_skeleton_sha256'] or
        canonical_sha256(candidate)!=bindings['candidate_sha256']):
        raise ValueError('character_preview_source_mismatch')
    doc,scope=build_preview(mesh,skeleton,bake,candidate)
    options={r['layer_id']:r for r in bindings['bindings']}
    originals={r['layer_id']:r for r in candidate['layers']}
    attachments=doc['skins'][0]['attachments'];rigid=[];pending=[]
    for record in draft['records']:
        name=record['layer_id']
        if record['action']!='bind':
            pending.append({'layer_id':name,'reason_code':'binding_'+record['action']})
            continue
        option=next(o for o in options[name]['options'] if o['id']==record['option_id'])
        if option['mode']!='rigid':continue
        local=option['setup_local'];x,y,r,b=originals[name]['bbox']
        attachments[name]={name:{'type':'region','path':name,'x':local['x'],'y':-local['y'],
                                'rotation':-local['rotation_degrees'],'width':r-x,'height':b-y}}
        doc['slots'].append({'name':name,'bone':option['bone_ids'][0],'attachment':name})
        rigid.append(name)
    order={r['layer_id']:i for i,r in enumerate(candidate['layers'])}
    doc['slots'].sort(key=lambda s:order[s['name']])
    included=[s['name'] for s in doc['slots']]
    unsupported=[{'layer_id':r['layer_id'],'reason_code':'selected_mesh_bake_required'} for r in draft['records']
                 if r['action']=='bind' and r['layer_id'] not in included]
    doc['skeleton']['hash']=canonical_sha256({'bake':bake,'bindings':bindings,'draft':draft})
    scope.update(schema='autospine.character-target-preview/v1',scope='confirmed_binding_subset',
                 source_bindings_sha256=canonical_sha256(bindings),source_draft_sha256=canonical_sha256(draft),
                 skeleton_json_sha256=canonical_sha256(doc),included_layers=included,rigid_layers=rigid,
                 excluded_layers=pending+unsupported,draw_order_status='source_order_unreviewed',
                 reason_codes=['cross_layer_seam_review_required']+(['remaining_layer_bindings_required']
                 if any(r['reason_code']!='binding_exclude' for r in pending+unsupported) else []))
    return doc,scope
