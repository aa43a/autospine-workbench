"""Source-bound triangle ownership suggestions, not pixel separation or binding."""
from copy import deepcopy
import math
from ..joints.joint_plane_weights import _planes
from ...resolved_project import canonical_sha256

ROLES = ('unknown', 'sleeve', 'cuff', 'hand', 'hanging_cloth')


def build(source, skeleton):
    raw_mesh = source.get('schema') == 'autospine.component-mesh-candidates/v1'
    if (source['schema'] not in ('autospine.component-axial-correction/v1', 'autospine.component-mesh-candidates/v1') or source.get('authority') != 'none'
            or source.get('production_authorized') is not False or source['skeleton_sha256'] != canonical_sha256(skeleton)):
        raise ValueError('sleeve_region_source_mismatch')
    if raw_mesh:
        from .sleeve_mesh_source import validate
        validate(source, skeleton)
    bones = {b['id']: b for b in skeleton['bones']}; records = []
    for row in source['records']:
        mesh = row['mesh']
        if not mesh or len(mesh['bone_ids']) != 3: continue
        if raw_mesh and not mesh['triangles']: continue
        ids = mesh['bone_ids']; side = ids[0][-1]
        # Supported canonical arm topology, independent of project or layer names.
        if ids != [f'upperarm_{side}', f'forearm_{side}', f'hand_{side}']: continue
        chain = [bones[b] for b in ids]
        if chain[1]['parent_id'] != ids[0] or chain[2]['parent_id'] != ids[1]:
            raise ValueError('sleeve_region_topology_mismatch')
        pivot, normal, _ = _planes(chain)[1]
        length = math.dist(chain[1]['head_xy'], chain[1]['tail_xy'])
        band = .12*length; assignments = []
        for index, tri in enumerate(mesh['triangles']):
            points = [mesh['vertices_xy'][v] for v in tri]
            axial = [sum((p[k]-pivot[k])*normal[k] for k in (0,1)) for p in points]
            lateral = [abs((p[0]-pivot[0])*normal[1]-(p[1]-pivot[1])*normal[0]) for p in points]
            role, reason = 'unknown', 'boundary_or_semantic_ambiguous'
            if max(axial) < -band: role, reason = 'sleeve', 'proximal_arm_geometry_only'
            elif min(axial) >= -band and max(axial) <= band: role, reason = 'cuff', 'wrist_band_geometry_only'
            elif min(axial) > band and max(lateral) <= band: role, reason = 'hand', 'distal_axis_geometry_only'
            # Crossing triangles and lateral distal fabric stay unknown: no forced cloth/hand guess.
            assignments.append(dict(triangle_id=index, suggested_role=role, reason_code=reason))
        records.append(dict(layer_id=row['layer_id'], component_id=row['component_id'],
                            source_image_sha256=row['source_image_sha256'], bone_ids=ids,
                            vertices_xy=deepcopy(mesh['vertices_xy']), triangles=deepcopy(mesh['triangles']),
                            suggestions=assignments))
    return dict(schema='autospine.sleeve-regions/v2' if raw_mesh else 'autospine.sleeve-regions/v1',
                profile='component-mesh-wrist-band12-v1' if raw_mesh else 'wrist-band12-triangle-suggestions-v1',
                project_id=source['project_id'], source_sha256=canonical_sha256(source),
                skeleton_sha256=canonical_sha256(skeleton), records=records,
                authority='none', production_authorized=False, semantic_confirmed=False)


def template(candidate):
    return dict(schema='autospine.sleeve-region-draft/v1', project_id=candidate['project_id'],
                candidate_sha256=canonical_sha256(candidate), authority='none', production_authorized=False,
                records=[dict(layer_id=r['layer_id'], component_id=r['component_id'], assignments=[
                    dict(triangle_id=s['triangle_id'], role='unknown', origin='pending') for s in r['suggestions']])
                    for r in candidate['records']])


def validate(value, candidate):
    expected = template(candidate)
    if (not isinstance(value, dict) or set(value) != set(expected)
            or any(value[k] != expected[k] for k in expected if k != 'records')
            or not isinstance(value['records'], list) or len(value['records']) != len(expected['records'])):
        raise ValueError('sleeve_draft_source_mismatch')
    for row, base, evidence in zip(value['records'], expected['records'], candidate['records']):
        if (not isinstance(row, dict) or set(row) != set(base) or row['layer_id'] != base['layer_id']
                or row['component_id'] != base['component_id'] or not isinstance(row['assignments'], list)
                or len(row['assignments']) != len(base['assignments'])):
            raise ValueError('sleeve_draft_inventory_mismatch')
        for item, original, suggestion in zip(row['assignments'], base['assignments'], evidence['suggestions']):
            if (not isinstance(item, dict) or set(item) != set(original) or type(item['triangle_id']) is not int
                    or item['triangle_id'] != original['triangle_id'] or item['role'] not in ROLES
                    or item['origin'] not in ('pending', 'geometry_prefill', 'manual_edit')
                    or item['origin'] == 'pending' and item['role'] != 'unknown'
                    or item['origin'] == 'geometry_prefill' and item['role'] != suggestion['suggested_role']):
                raise ValueError('sleeve_draft_assignment_invalid')
    return deepcopy(value)
