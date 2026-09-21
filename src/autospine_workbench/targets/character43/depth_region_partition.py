"""Independent render regions with exact source triangles and deformation indices."""
from copy import deepcopy

from .depth_overlap_ownership import triangle_groups

PROFILE = 'ordered-weight-ownership-regions-v1'


def build(document, selected_slots, *, part_limit=128, triangle_labels=None):
    """Split consecutive ownership runs, preserving original triangle draw sequence.

    This creates an experimental render representation, not inferred garment depth.
    Full vertex/UV/influence arrays deliberately preserve sparse deform offsets.
    """
    names = [s['name'] for s in document['slots']]
    selected = set(selected_slots)
    if triangle_labels is not None and set(triangle_labels)!=selected:
        raise ValueError('depth_partition_label_slots')
    if not selected or not selected <= set(names) or len(names) != len(set(names)):
        raise ValueError('depth_partition_slots_invalid')
    if len(document['skins']) != 1:
        raise ValueError('depth_partition_single_skin_required')
    skin = document['skins'][0]
    for attachments in skin['attachments'].values():
        if any(a.get('type') in ('clipping', 'linkedmesh') for a in attachments.values()):
            raise ValueError('depth_partition_linked_or_clipped_unsupported')
    for animation in document['animations'].values():
        if animation.get('drawOrder') or animation.get('draworder'):
            raise ValueError('depth_partition_existing_order_preserved')
        if selected & animation.get('slots', {}).keys():
            raise ValueError('depth_partition_slot_timeline_unsupported')
    candidate = deepcopy(document)
    target_skin = candidate['skins'][0]['attachments']
    rows = []; output_slots = []
    for slot in document['slots']:
        name = slot['name']
        if name not in selected:
            output_slots.append(deepcopy(slot)); continue
        attachment_name = slot['attachment']
        attachments = skin['attachments'][name]
        if set(attachments) != {attachment_name}:
            raise ValueError('depth_partition_single_attachment_required')
        mesh = attachments[attachment_name]
        if len(mesh.get('triangles', [])) % 3:
            raise ValueError('depth_partition_triangle_indices_invalid')
        groups, bones = triangle_groups(document, mesh)
        owner = {t: group for group, triangles in groups.items() for t in triangles}
        if triangle_labels is not None:
            labels=triangle_labels[name]
            if (len(labels)!=len(mesh['triangles'])//3
                    or any(not isinstance(v,str) or not v for v in labels)):
                raise ValueError('depth_partition_label_inventory')
            old_owner=owner;owner=dict(enumerate(labels));new_bones={}
            for triangle,group in owner.items():
                new_bones.setdefault(group,set()).update(bones[old_owner[triangle]])
            bones=new_bones
        runs = []
        for triangle in range(len(mesh['triangles'])//3):
            group = owner[triangle]
            if not runs or runs[-1]['group'] != group:
                runs.append(dict(group=group, triangles=[]))
            runs[-1]['triangles'].append(triangle)
        if not runs or len(rows)+len(runs) > part_limit:
            raise ValueError('depth_partition_part_limit')
        del target_skin[name]
        new_names = []
        for index, run in enumerate(runs):
            new_name = name+'-depth-'+str(index+1).zfill(3)
            if new_name in names or new_name in target_skin:
                raise ValueError('depth_partition_slot_collision')
            new_names.append(new_name)
            output_slots.append(dict(deepcopy(slot), name=new_name, attachment=new_name))
            part = deepcopy(mesh)
            part['path'] = mesh.get('path', attachment_name)
            part['triangles'] = [v for t in run['triangles'] for v in mesh['triangles'][3*t:3*t+3]]
            # Editor hull/edge metadata describes the old complete mesh.
            part.pop('hull', None); part.pop('edges', None)
            target_skin[new_name] = {new_name: part}
            rows.append(dict(source_slot=name, slot=new_name, **run,
                             bones=sorted(bones[run['group']]),
                             depth_status='unassigned', authority='none'))
        for animation in candidate['animations'].values():
            for skin_tracks in animation.get('attachments', {}).values():
                if name in skin_tracks:
                    tracks = skin_tracks.pop(name)
                    if set(tracks) != {attachment_name}:
                        raise ValueError('depth_partition_attachment_timeline_unsupported')
                    for new_name in new_names:
                        skin_tracks[new_name] = {new_name: deepcopy(tracks[attachment_name])}
    candidate['slots'] = output_slots
    report = dict(profile=PROFILE, selected=False, authority='none', regions=rows,
                  triangle_order_preserved=True, deformation_index_space_preserved=True,
                  scope='render_partition_candidate_not_depth_inference_or_runtime_acceptance')
    if triangle_labels is not None:report['profile']='ordered-explicit-triangle-regions-v1'
    return candidate, report
