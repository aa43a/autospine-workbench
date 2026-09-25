"""Same-time counterfactuals separate attachment jumps from source movement."""
import math

from ...resolved_project import canonical_sha256
from .active_mesh_pose import sample_active


def inspect(document, variant):
    slot, animation = variant['slot'], variant['animation']
    names = [variant['original_attachment'], variant['variant_attachment']]
    meshes = document['skins'][0]['attachments'][slot]
    first, second = (meshes[name] for name in names)
    # This compiler preserves vertex correspondence. Do not compare unrelated
    # topology by array index or silently substitute a nearest-point mapping.
    compatible = (first['triangles'] == second['triangles'] and
                  len(first['uvs']) == len(second['uvs']))
    documents = []
    motion = document['animations'][animation]
    for name in names:
        channels = {**motion.get('slots', {})}
        channels[slot] = {**channels.get(slot, {}), 'attachment': [dict(time=0, name=name)]}
        documents.append({**document, 'animations': {
            **document['animations'], animation: {**motion, 'slots': channels}}})
    rows = []
    for index, time in enumerate(variant['runtime_interval']):
        original, alternate = [sample_active(doc, animation, time)['vertices'][slot] for doc in documents]
        distances = [math.dist(a, b) for a, b in zip(original, alternate)] if compatible else []
        rows.append(dict(time=time, direction='enter' if index == 0 else 'exit',
                         maximum_vertex_jump_px=max(distances) if distances else None,
                         changed_vertices=sum(d>1e-6 for d in distances),
                         geometry_status=('unchanged_within_tolerance' if max(distances,default=0)<=1e-6
                                          else 'discontinuous') if compatible else 'correspondence_required'))
    uv_error = max((abs(a-b) for a,b in zip(first['uvs'],second['uvs'])),default=0) if compatible else None
    return dict(profile='same-time-view-switch-continuity-v1',
                skeleton_sha256=canonical_sha256(document), slot=slot, animation=animation,
                original_attachment=names[0], variant_attachment=names[1], records=rows,
                maximum_uv_change=uv_error, texture_paths=[m.get('path',n) for m,n in zip((first,second),names)],
                material_status='requires_rendered_boundary_review', selected=False, authority='none',
                scope='same_time_vertex_correspondence_not_alpha_color_occlusion_or_visual_acceptance')
