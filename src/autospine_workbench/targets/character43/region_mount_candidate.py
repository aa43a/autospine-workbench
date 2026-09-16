"""Mount existing static regions without repartitioning textures or changing draw order."""
from copy import deepcopy
from hashlib import sha256
import json
from ...resolved_project import canonical_sha256
from ...automation.storage_io import canonical_bytes
from .affine_pose import sample, matrices
from .skirt_candidate import inverse
from .numeric_reference import read, write
from .deformation_qa import inspect


def generate(files, decision):
    source = canonical_sha256({n:sha256(raw).hexdigest() for n,raw in files.items()})
    from ...automation.character_region_mounts import valid_decision
    if not valid_decision(decision) or decision['source_bundle_sha256'] != source:
        raise ValueError('region_mount_decision_source')
    doc=json.loads(files['skeleton.json']);manifest=json.loads(files['character-manifest.json'])
    if doc['skeleton']['spine']!='4.3.26' or len(doc['skins'])!=1:
        raise ValueError('region_mount_target')
    choices=decision['parents']; bones={b['name']:i for i,b in enumerate(doc['bones'])}
    available={r['region_id'] for l in manifest['layers'] for r in l['regions'] if r['state']=='static_reference'}
    if not choices.keys() <= available or not set(choices.values()) <= bones.keys():
        raise ValueError('region_mount_scope')
    setup=dict(doc,animations={'setup':{}});positions,_=sample(setup,'setup',0)
    transforms=matrices(setup,'setup',0)
    for slot,parent in choices.items():
        for animation in doc['animations'].values():
            if (animation.get('drawOrder') or animation.get('draworder') or slot in animation.get('slots',{})
                    or any(slot in skin for skin in animation.get('attachments',{}).values())):
                raise ValueError('region_mount_animated_dependency')
        attachment=doc['skins'][0]['attachments'][slot][slot];vertices=attachment['vertices']
        if not vertices or len(vertices)%5 or any(vertices[i]!=1 or vertices[i+4]!=1 or vertices[i+1]!=vertices[1]
                                                 for i in range(0,len(vertices),5)):
            raise ValueError('region_mount_static_weights')
        attachment['vertices']=[v for point in positions[slot] for v in (1,bones[parent],*inverse(transforms[parent],point),1)]
    output=dict(files);output['skeleton.json']=canonical_bytes(doc)
    if 'editor/skeleton.json' in files:
        editor=deepcopy(doc);editor['skeleton']['images']='./images/'
        output['editor/skeleton.json']=canonical_bytes(editor)
    after,_=sample(dict(doc,animations={'setup':{}}),'setup',0)
    if any(abs(a-b)>1e-6 for slot in choices for p,q in zip(positions[slot],after[slot]) for a,b in zip(p,q)):
        raise ValueError('region_mount_setup_changed')
    reference=read(files)
    for animation,frames in reference['animations'].items():
        for frame in frames:
            current,_=sample(doc,animation,frame['time'])
            for slot,points in frame['vertices'].items():
                if slot not in choices and (len(current[slot])!=len(points) or any(abs(a-b)>1e-6 for p,q in zip(current[slot],points) for a,b in zip(p,q))):
                    raise ValueError('region_mount_context_changed')
            frame['vertices'].update({slot:current[slot] for slot in choices})
    reference['skeleton_sha256']=sha256(output['skeleton.json']).hexdigest();output=write(output,reference)
    qa=inspect(output);output['deformation.json']=canonical_bytes(qa)
    for layer in manifest['layers']:
        if not any(r['region_id'] in choices for r in layer['regions']):continue
        for region in layer['regions']:
            if region['region_id'] in choices:region['state']='weighted_candidate'
        unresolved=any(r['state']=='static_reference' for r in layer['regions'])
        layer['state']='partial' if unresolved else 'weighted_candidate'
        layer['reason_codes']=['unmounted_regions_retained'] if unresolved else []
    report=dict(schema='autospine.region-mount-result/v1',source_bundle_sha256=source,
        parents=choices,geometry_passed=qa['passed'],draw_order='unchanged',textures='unchanged',
        authority='none',production_authorized=False)
    output['region-mount.json']=canonical_bytes(report)
    output['region-mount-decision.json']=canonical_bytes(decision)
    manifest.update(profile='existing-region-mount-v1',source_character_sha256=source,
                    authority='none',production_authorized=False,status='needs_review',qa={'runtime_status':'not_run'})
    manifest['files']={n:sha256(raw).hexdigest() for n,raw in output.items() if n!='character-manifest.json'}
    output['character-manifest.json']=canonical_bytes(manifest)
    return output,report
