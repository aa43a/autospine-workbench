"""Resolve immutable textures for overlap preflight without changing assets."""
from hashlib import sha256
from io import BytesIO
import numpy as np
from PIL import Image
from ..targets.character43.occlusion_scope_alpha import inspect


def read(document, files, pose, slot, reference, selected, animation):
    names=(slot,reference); slots={s['name']:s for s in document['slots']}
    motion=document['animations'][animation]
    if any(slots[s].get('color','ffffffff')!='ffffffff' or slots[s].get('blend','normal')!='normal'
           or motion.get('slots',{}).get(s) for s in names):
        return dict(status='tint_blend_or_slot_animation_unsupported',visual_status='not_checked')
    meshes=document['skins'][0]['attachments']; textures=[]; identities={}
    for s in names:
        mesh=meshes[s][s]
        if mesh.get('color','ffffffff')!='ffffffff':
            return dict(status='attachment_tint_unsupported',visual_status='not_checked')
        path='images/'+mesh.get('path',s)+'.png'
        if path not in files:return dict(status='texture_unavailable',visual_status='not_checked')
        raw=files[path]; identities[path]=sha256(raw).hexdigest()
        with Image.open(BytesIO(raw)) as image:textures.append(np.asarray(image.convert('RGBA'))[:,:,3])
    result=inspect(pose['vertices'][slot],meshes[slot][slot]['uvs'],pose['triangles'][slot],selected,
                   pose['vertices'][reference],meshes[reference][reference]['uvs'],pose['triangles'][reference],*textures)
    result['textures']=identities
    return result
