"""Same-time material-coordinate displacement at pose attachment switches.

Different vertex counts cannot be compared by index. Both mesh UV surfaces are
sampled at vertices and triangle centroids. Missing or multi-valued mappings
remain unresolved; no nearest-point substitution or visual acceptance is used.
"""
from copy import deepcopy
import math

from ...resolved_project import canonical_sha256
from .active_mesh_pose import sample_active


def _map(uv, uvs, triangles, points):
    hits = []
    for a, b, c in triangles:
        pa, pb, pc = uvs[a], uvs[b], uvs[c]
        x, y = pb[0]-pa[0], pb[1]-pa[1]
        u, v = pc[0]-pa[0], pc[1]-pa[1]
        determinant = x*v-y*u
        if abs(determinant) < 1e-14:
            continue
        dx, dy = uv[0]-pa[0], uv[1]-pa[1]
        wb, wc = (dx*v-dy*u)/determinant, (x*dy-y*dx)/determinant
        wa = 1-wb-wc
        if min(wa, wb, wc) < -1e-8:
            continue
        point = [sum(w*points[i][k] for w, i in ((wa,a),(wb,b),(wc,c))) for k in (0,1)]
        if not any(math.dist(point, old) <= 1e-5 for old in hits):
            hits.append(point)
    return hits


def compare_surfaces(mesh_a, points_a, mesh_b, points_b):
    surfaces = []
    probes = set()
    for mesh, points in ((mesh_a, points_a), (mesh_b, points_b)):
        uvs = [mesh['uvs'][i:i+2] for i in range(0, len(mesh['uvs']), 2)]
        flat = mesh['triangles']
        triangles = [flat[i:i+3] for i in range(0, len(flat), 3)]
        if len(uvs) != len(points):
            raise ValueError('pose_transition_vertex_mismatch')
        probes.update(tuple(p) for p in uvs)
        probes.update(tuple(sum(uvs[v][k] for v in tri)/3 for k in (0,1)) for tri in triangles)
        surfaces.append((uvs, triangles, points))
    if len(probes) > 4096:
        raise ValueError('pose_transition_probe_budget')
    records = []
    for uv in sorted(probes):
        a, b = [_map(uv, *surface) for surface in surfaces]
        status = 'uncovered_uv' if not a or not b else 'ambiguous_uv' if len(a)!=1 or len(b)!=1 else 'measured'
        record = dict(uv=list(uv), status=status, source_hits=len(a), target_hits=len(b))
        if status == 'measured':
            record.update(displacement_px=math.dist(a[0], b[0]), before=a[0], after=b[0])
        records.append(record)
    measured = [r for r in records if r['status']=='measured']
    return dict(probes=len(records), unresolved=sum(r['status']!='measured' for r in records),
        maximum_displacement_px=max((r['displacement_px'] for r in measured), default=None),
        worst=max(measured, key=lambda r:r['displacement_px'], default=None), records=records,
        scope='sampled_uv_geometry_not_alpha_color_or_continuous_surface_proof')


def inspect(document, report):
    if canonical_sha256(document) != report['output_sha256']:
        raise ValueError('pose_transition_document_changed')
    slot, animation = report['slot'], report['animation']
    original, variant = report['original_attachment'], report['variant_attachment']
    meshes = document['skins'][0]['attachments'][slot]
    if meshes[original].get('path', original) != meshes[variant].get('path', variant):
        raise ValueError('pose_transition_shared_texture_required')
    records = []
    for time, names in zip(report['runtime_interval'], ((original, variant), (variant, original))):
        surfaces = []
        for name in names:
            forced = deepcopy(document)
            forced['animations'][animation].setdefault('slots', {}).setdefault(slot, {})['attachment'] = [dict(time=0, name=name)]
            surfaces.append(sample_active(forced, animation, time)['vertices'][slot])
        records.append(dict(time=time, from_attachment=names[0], to_attachment=names[1],
            **compare_surfaces(meshes[names[0]], surfaces[0], meshes[names[1]], surfaces[1])))
    return dict(profile='pose-variant-uv-transition-v1', source_sha256=report['output_sha256'],
        records=records, authority='none', selected=False, visual_status='not_evaluated')
