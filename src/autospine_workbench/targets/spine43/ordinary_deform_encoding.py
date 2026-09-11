"""Encode the validated ordinary world-delta row without changing legacy targets."""
import math
from ...asset.planning.sleeve_helpers import frames
from ...asset.planning.ordinary_sleeve import angles
from ...asset.planning.ordinary_deform_sampling import dense_offsets
from .sleeve_deform import local_offsets


def encode(row, mesh, skeleton, source_sha):
    bones = []
    seen = set()
    for bone in skeleton['bones']:
        local = bone['setup_local']; parent = bone['parent_id']
        if bone['id'] in seen or parent is not None and parent not in seen:
            raise ValueError('ordinary_target_bone_topology')
        # Current canonical skeleton is rigid: no implicit scale/shear support.
        if (set(local) != {'x','y','rotation_degrees'}
                or set(bone)&{'scale','scale_x','scale_y','shear','shear_x','shear_y','transform','inherit'}):
            raise ValueError('ordinary_target_transform_unsupported')
        values = [local['x'],local['y'],local['rotation_degrees'],bone['length']]
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):
            raise ValueError('ordinary_target_transform_nonfinite')
        item = dict(name=bone['id'],x=local['x'],y=-local['y'],rotation=-local['rotation_degrees'],length=bone['length'])
        if parent is not None: item['parent'] = parent
        bones.append(item); seen.add(bone['id'])
    indices = {b['name']:i for i,b in enumerate(bones)}
    vertices = []
    for entries in row['weights']:
        vertices.append(len(entries))
        for entry in entries:
            vertices.extend([indices[entry['bone_id']],entry['local_xy'][0],-entry['local_xy'][1],entry['weight']])
    uvs = mesh.get('uvs')
    if (not isinstance(uvs,list) or len(uvs)!=len(row['weights'])
            or any(not isinstance(p,list) or len(p)!=2 or any(type(v) not in (int,float)
                       or not math.isfinite(v) or not 0<=v<=1 for v in p) for p in uvs)):
        raise ValueError('ordinary_target_uv_inventory')
    if mesh['vertices_xy']!=row['setup_vertices'] or mesh['triangles']!=row['triangles']:
        raise ValueError('ordinary_target_geometry_identity')
    lookup = {b['id']:b for b in skeleton['bones']}; chain = [lookup[b] for b in row['bone_ids']]
    name = row['layer_id']+'-'+row['component_id']; animations = {}
    for track in row['tracks']:
        rotation = {b:{'rotate':[]} for b in track['drivers']}; deform = []
        dense = dense_offsets(track['keys'],len(row['weights']))
        for tick,delta in enumerate(dense):
            values = angles(track['amplitudes'],tick)
            transforms = frames(chain,dict(zip(track['drivers'],values)))
            for driver,value in zip(track['drivers'],values):
                rotation[driver]['rotate'].append(dict(time=tick/64,value=-value))
            deform.append(dict(time=tick/64,vertices=local_offsets(row['weights'],delta,transforms)))
        animations[track['bone_id']] = dict(bones=rotation,attachments={'default':{name:{name:{'deform':deform}}}})
    width,height = skeleton['canvas']
    return dict(skeleton=dict(spine='4.3.26',hash=source_sha,images='./images/',x=0,y=-height,width=width,height=height,fps=64),
        bones=bones,slots=[dict(name=name,bone=chain[1]['id'],attachment=name)],constraints=[],
        skins=[dict(name='default',attachments={name:{name:dict(type='mesh',path=name,
            uvs=[v for p in uvs for v in p],vertices=vertices,triangles=[v for t in row['triangles'] for v in t])}})],
        animations=animations)
