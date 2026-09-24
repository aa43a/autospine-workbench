"""Apply experimental foot frame compensation only to explicit pure-foot meshes."""
from copy import deepcopy
from ...resolved_project import canonical_sha256
from .deform_addition import entries


def build(document, adjusted, animation, bindings):
    if not bindings or set(bindings.values())-{'foot_l','foot_r'}:
        raise ValueError('foot_surface_bindings_invalid')
    def strip(doc):
        value=deepcopy(doc)
        for name in set(bindings.values()):
            value['animations'][animation].get('bones',{}).pop(name,None)
        return value
    if strip(document)!=strip(adjusted):
        raise ValueError('foot_surface_changes_outside_foot_tracks')
    if len(document['skins'])!=1:raise ValueError('foot_surface_single_skin_required')
    result=deepcopy(document);names=[b['name'] for b in document['bones']];mapping={}
    for bone in sorted(set(bindings.values())):
        helper=bone+'-material'
        if helper in names:raise ValueError('foot_surface_helper_exists')
        index=names.index(bone);new_index=len(result['bones'])
        result['bones'].append(dict(document['bones'][index],name=helper))
        mapping[bone]=dict(name=helper,index=new_index,original_index=index)
        for name,motion in result['animations'].items():
            source=adjusted if name==animation else document
            channels=source['animations'][name].get('bones',{}).get(bone)
            if channels is not None:motion.setdefault('bones',{})[helper]=deepcopy(channels)
    for slot,bone in bindings.items():
        choices=result['skins'][0]['attachments'].get(slot)
        if not choices:raise ValueError('foot_surface_slot_missing')
        original=mapping[bone]['original_index']
        for mesh in choices.values():
            if mesh.get('type')!='mesh' or mesh.get('parent'):raise ValueError('foot_surface_mesh_required')
            if any(index!=original for row in entries(mesh) for index,weight in row if weight>0):
                raise ValueError('foot_surface_mixed_mesh_rejected')
            values=mesh['vertices'];cursor=0
            while cursor<len(values):
                count=values[cursor];cursor+=1
                for _ in range(count):
                    if values[cursor]==original:values[cursor]=mapping[bone]['index']
                    cursor+=4
    return result,dict(profile='isolated-foot-surface-frame-v1',authority='none',selected=False,
        input_sha256=canonical_sha256(document),adjusted_sha256=canonical_sha256(adjusted),
        output_sha256=canonical_sha256(result),bindings=bindings,helpers=mapping,
        scope='explicit_shoe_mesh_frame_isolation_seams_and_runtime_unverified')
