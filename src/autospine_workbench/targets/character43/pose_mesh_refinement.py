"""Interior pose controls preserving the original weighted surface exactly.

Each selected triangle gains a centroid. Boundary edges are unchanged, so no
neighbor needs subdivision. New influences deliberately retain separate source
entries, including repeated bones: merging them would change deform semantics.
This is preparation for authored pose correction, not a deformation repair.
"""
from copy import deepcopy
import math

from ...resolved_project import canonical_sha256


def refine(document, slot, triangles, document_sha256):
    if canonical_sha256(document) != document_sha256:
        raise ValueError('pose_refinement_document_changed')
    if len(document['skins']) != 1:
        raise ValueError('pose_refinement_single_skin_required')
    skin = document['skins'][0]
    mesh = skin['attachments'][slot][slot]
    if mesh.get('type') != 'mesh' or mesh.get('parent'):
        raise ValueError('pose_refinement_mesh_required')
    if any(a.get('parent') == slot for s in document['skins']
           for attachments in s['attachments'].values() for a in attachments.values()):
        raise ValueError('pose_refinement_linked_mesh_unsupported')
    flat = mesh['triangles']
    count = len(mesh['uvs']) // 2
    if (len(flat) % 3 or len(mesh['uvs']) % 2 or
            any(type(i) is not int or not 0 <= i < count for i in flat)):
        raise ValueError('pose_refinement_topology_invalid')
    if (not isinstance(triangles, list) or not triangles or len(triangles) > 512 or
            len(set(triangles)) != len(triangles) or
            any(type(i) is not int or not 0 <= i < len(flat)//3 for i in triangles)):
        raise ValueError('pose_refinement_selection_invalid')
    rows, offsets, cursor, deform_size = [], [], 0, 0
    data = mesh['vertices']
    for _ in range(count):
        n = data[cursor]; cursor += 1
        if type(n) is not int or n < 1 or cursor + 4*n > len(data):
            raise ValueError('pose_refinement_weighted_mesh_required')
        row = [data[j:j+4] for j in range(cursor, cursor+4*n, 4)]
        if any(type(b) is not int or not 0 <= b < len(document['bones']) or
               not all(math.isfinite(v) for v in (x, y, w)) or w < 0
               for b, x, y, w in row) or abs(sum(r[3] for r in row)-1) > 1e-6:
            raise ValueError('pose_refinement_weights_invalid')
        offsets.append((deform_size, deform_size+2*n))
        deform_size += 2*n
        rows.append(row); cursor += 4*n
    if cursor != len(data):
        raise ValueError('pose_refinement_vertex_count_invalid')
    result = deepcopy(document)
    target = result['skins'][0]['attachments'][slot][slot]
    selected = set(triangles)
    sources, mapped, output = [], [], []
    for index in range(len(flat)//3):
        a, b, c = flat[3*index:3*index+3]
        if index not in selected:
            output.extend((a, b, c)); mapped.append(index)
            continue
        center = count + len(sources)
        sources.append([a, b, c])
        influences = [r for v in (a, b, c) for r in rows[v]]
        target['vertices'].append(len(influences))
        for bone, x, y, weight in influences:
            target['vertices'].extend((bone, x, y, weight/3))
        target['uvs'].extend(sum(mesh['uvs'][2*v+k] for v in (a, b, c))/3 for k in (0, 1))
        output.extend((a, b, center, b, c, center, c, a, center))
        mapped.extend((index, index, index))
    target['triangles'] = output
    skin_name = skin.get('name', 'default')
    for animation in result['animations'].values():
        if animation.get('deform'):
            raise ValueError('pose_refinement_legacy_deform_unsupported')
        keys = animation.get('attachments', {}).get(skin_name, {}).get(slot, {}).get(slot, {}).get('deform', [])
        for key in keys:
            if key.get('curve') is not None:
                raise ValueError('pose_refinement_linear_deform_required')
            start, values = key.get('offset', 0), key.get('vertices', [])
            if (type(start) is not int or start < 0 or start+len(values) > deform_size or
                    not all(math.isfinite(v) for v in values)):
                raise ValueError('pose_refinement_deform_invalid')
            dense = [0.]*deform_size
            dense[start:start+len(values)] = values
            extension = [value for group in sources for v in group
                         for value in dense[offsets[v][0]:offsets[v][1]]]
            key.pop('offset', None)
            key['vertices'] = dense + extension
    return result, dict(profile='interior-pose-mesh-refinement-v1', authority='none', selected=False,
        input_sha256=document_sha256, output_sha256=canonical_sha256(result), slot=slot,
        source_vertex_count=count, added_vertex_sources=sources, triangle_sources=mapped,
        boundary_edges_unchanged=True, repair_claim=False)
