"""Separate 4.3.26 diagnostic subset adapter; no extension of certified rig profiles."""
from ...resolved_project import canonical_sha256
from ...asset.joints.elbow_bake import validate_bake


def build_preview(mesh,skeleton,bake,candidate):
    validate_bake(mesh,skeleton,bake)
    if canonical_sha256(candidate)!=skeleton['candidate_sha256']:
        raise ValueError('elbow_preview_source_mismatch')
    indices={b['id']:i for i,b in enumerate(skeleton['bones'])}
    bones=[]
    for bone in skeleton['bones']:
        local=bone['setup_local']
        row={'name':bone['id'],'x':local['x'],'y':-local['y'],
             'rotation':-local['rotation_degrees'],'length':bone['length']}
        if bone['parent_id'] is not None:row['parent']=bone['parent_id']
        bones.append(row)
    layers={r['layer_id']:r for r in mesh['layers']}
    originals={r['layer_id']:r for r in candidate['layers']}
    slots,attachments,timelines,tracks=[],{},{},{}
    excluded=[]
    for baked in bake['layers']:
        name=baked['layer_id']
        if baked['status']!='passed':
            excluded.append({'layer_id':name,'reason_code':'mesh_bake_not_passed'})
            continue
        row=layers[name];original=originals[name];vertices=[]
        for influences in row['weights']:
            vertices.append(len(influences))
            for influence in influences:
                x,y=influence['local_xy']
                vertices.extend([indices[influence['bone_id']],x,-y,influence['weight']])
        slots.append({'name':name,'bone':row['weights'][0][0]['bone_id'],'attachment':name})
        attachments[name]={name:{'type':'mesh','path':name,'uvs':[v for p in row['uvs'] for v in p],
            'triangles':[v for t in row['triangles'] for v in t], 'vertices':vertices,
            'width':original['bbox'][2]-original['bbox'][0],'height':original['bbox'][3]-original['bbox'][1]}}
        keys=[{'time':i/30,'vertices':[value for vertex in key['offsets'] for x,y in vertex for value in (x,-y)]}
              for i,key in enumerate(baked['frames'])]
        timelines[name]={name:{'deform':keys}}
        joint=row['weights'][0][1]['bone_id']
        track={'rotate':[{'time':i/30,'value':-key['angle']} for i,key in enumerate(baked['frames'])]}
        if joint in tracks and tracks[joint]!=track:raise ValueError('elbow_preview_track_conflict')
        tracks[joint]=track
    if not slots:raise ValueError('elbow_preview_mesh_required')
    document={'skeleton':{'spine':'4.3.26','hash':canonical_sha256(bake),'images':'./images/',
               'x':0,'y':-candidate['canvas'][1],'width':candidate['canvas'][0],'height':candidate['canvas'][1],'fps':30},
              'bones':bones,'slots':slots,'skins':[{'name':'default','attachments':attachments}],
              'constraints':[],'animations':{'elbow-diagnostic':{'bones':tracks,'attachments':{'default':timelines}}}}
    scope={'schema':'autospine.elbow-target-preview/v1','authority':'none','production_authorized':False,
           'target':'4.3.26','scope':'selected_mesh_layers_only','source_bake_sha256':canonical_sha256(bake),
           'skeleton_json_sha256':canonical_sha256(document),'included_layers':[s['name'] for s in slots],
           'excluded_layers':excluded,'full_character_status':'blocked','seam_status':'not_evaluated',
           'reason_codes':['remaining_layer_bindings_required','cross_layer_seam_review_required'],
           'runtime_status':'not_evaluated'}
    return document,scope
