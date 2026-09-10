"""Uncorrected ordinary-sleeve FK envelope: no helper or fabricated cloth role."""
from copy import deepcopy
import math

from .component_distal_guard import inventory
from .component_local_solver import metrics
from .component_temporal_qa import passed
from .sleeve_helpers import frames
from ..joints.mesh_weights import _deform, _rotate, _area
from ...resolved_project import canonical_sha256

SCHEMA = 'autospine.ordinary-sleeve-motion/v1'
PROFILE = 'ordinary-forearm30-hand30-sine129-v1'
MOTIONS = (('forearm', (30, 0)), ('hand', (0, 30)),
           ('combined_same', (30, 30)), ('combined_opposed', (30, -30)))


def angles(amplitudes, tick):
    if type(tick) not in (int, float) or not math.isfinite(tick) or not 0 <= tick <= 128:
        raise ValueError('ordinary_sleeve_tick_invalid')
    phase = 0. if tick in (0, 64, 128) else math.sin(2*math.pi*tick/128)
    return [float(amplitude)*phase for amplitude in amplitudes]


def _validate_mesh(mesh, chain):
    points, triangles, weights = mesh['vertices_xy'], mesh['triangles'], mesh['weights']
    ids = [b['id'] for b in chain]
    if not points or not triangles or len(points) != len(weights):
        raise ValueError('ordinary_sleeve_mesh_invalid')
    for bone in chain:
        values = bone['head_xy'] + bone['tail_xy'] + [bone['world_rotation_degrees']]
        if len(values) != 5 or any(type(x) not in (int, float) or not math.isfinite(x) for x in values):
            raise ValueError('ordinary_sleeve_bone_invalid')
        if math.dist(bone['head_xy'], bone['tail_xy']) < 1e-7:
            raise ValueError('ordinary_sleeve_bone_invalid')
    for p, entries in zip(points, weights):
        if len(p) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) for x in p):
            raise ValueError('ordinary_sleeve_mesh_invalid')
        if [w['bone_id'] for w in entries] != ids:
            raise ValueError('ordinary_sleeve_influence_inventory')
        for w in entries:
            if (type(w['weight']) not in (int, float) or not math.isfinite(w['weight']) or not 0 <= w['weight'] <= 1
                    or len(w['local_xy']) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) for x in w['local_xy'])):
                raise ValueError('ordinary_sleeve_weight_invalid')
    for tri in triangles:
        if (len(tri) != 3 or len(set(tri)) != 3 or any(type(i) is not int or not 0 <= i < len(points) for i in tri)
                or abs(_area(points, tri)) < 1e-12):
            raise ValueError('ordinary_sleeve_triangle_invalid')


def track(mesh, chain, name, amplitudes):
    drivers = [chain[1]['id'], chain[2]['id']]
    qa, samples = [], []
    first = last = None
    for tick in range(129):
        values = angles(amplitudes, tick)
        transforms = frames(chain, dict(zip(drivers, values)))
        points = _deform(mesh['weights'], transforms)
        if any(not math.isfinite(x) for p in points for x in p):
            raise ValueError('ordinary_sleeve_nonfinite_deformation')
        qa.append(metrics(mesh['vertices_xy'], points, mesh['triangles']))
        if first is None: first = points
        last = points
        if tick % 4 == 0:
            bones = []
            for b in chain:
                head, rotation = transforms[b['id']]
                offset = _rotate([math.dist(b['head_xy'], b['tail_xy']), 0], rotation)
                bones.append(dict(id=b['id'], head_xy=head, tail_xy=[head[k]+offset[k] for k in (0, 1)]))
            samples.append(dict(tick=tick, time=tick/64, angles=values, points=points, bones=bones))
    return dict(bone_id=name, drivers=drivers, amplitudes=list(amplitudes), angle_range=[-30, 30],
                qa=qa, samples=samples, failed_ticks=sum(not passed(q) for q in qa),
                correction_selected=False, loop_error=max(math.dist(a, b) for a, b in zip(first, last)))


def build(source, draft, skeleton):
    if (source.get('schema') != 'autospine.sleeve-weights/v1'
            or draft.get('schema') != 'autospine.sleeve-region-draft/v1'
            or source.get('draft_sha256') != canonical_sha256(draft)
            or source.get('candidate_sha256') != draft.get('candidate_sha256')
            or source.get('skeleton_sha256') != canonical_sha256(skeleton)
            or source.get('project_id') != draft.get('project_id')
            or any(d.get('authority') != 'none' or d.get('production_authorized') is not False for d in (source, draft))):
        raise ValueError('ordinary_sleeve_source_mismatch')
    labels = inventory(draft['records']); sources = inventory(source['records'])
    if not labels.keys() <= sources.keys():
        raise ValueError('ordinary_sleeve_region_inventory')
    bones = {b['id']: b for b in skeleton['bones']}
    if len(bones) != len(skeleton['bones']):
        raise ValueError('ordinary_sleeve_duplicate_bone')
    rows = []
    for key, original in sources.items():
        row = dict(layer_id=key[0], component_id=key[1], status='blocked', reason_codes=[])
        rows.append(row)
        if key not in labels or original['mesh'] is None:
            row['reason_codes'] = ['ordinary_sleeve_region_unavailable']; continue
        mesh = original['mesh']; items = labels[key]['assignments']; roles = set()
        if len(items) != len(mesh['triangles']):
            raise ValueError('ordinary_sleeve_assignment_inventory')
        for i, item in enumerate(items):
            if (type(item.get('triangle_id')) is not int or item['triangle_id'] != i
                    or item.get('role') not in ('sleeve', 'cuff', 'hand', 'hanging_cloth', 'unknown')
                    or item.get('origin') not in ('pending', 'manual_edit', 'geometry_prefill')
                    or item['origin'] == 'pending' and item['role'] != 'unknown'):
                raise ValueError('ordinary_sleeve_assignment_invalid')
            roles.add(item['role'])
        if 'hanging_cloth' in roles:
            row['reason_codes'] = ['ordinary_sleeve_drape_branch_required']; continue
        if not {'sleeve', 'cuff'} <= roles:
            row['reason_codes'] = ['ordinary_sleeve_roles_required']; continue
        ids = mesh['bone_ids']
        suffix = ids[0][-1] if ids else ''
        if (ids != [f'{name}_{suffix}' for name in ('upperarm', 'forearm', 'hand')]
                or suffix not in ('l', 'r') or any(b not in bones for b in ids)
                or any(bones[ids[i]]['parent_id'] != ids[i-1] for i in (1, 2))):
            raise ValueError('ordinary_sleeve_chain_invalid')
        chain = [bones[b] for b in ids]; _validate_mesh(mesh, chain)
        setup = _deform(mesh['weights'], frames(chain, {}))
        setup_error = max(math.dist(a, b) for a, b in zip(mesh['vertices_xy'], setup))
        sum_error = max(abs(sum(w['weight'] for w in entries)-1) for entries in mesh['weights'])
        tracks = [track(mesh, chain, name, amplitudes) for name, amplitudes in MOTIONS]
        reasons = []
        if 'unknown' in roles: reasons.append('ownership_review_required')
        if setup_error > 1e-7: reasons.append('setup_reconstruction_failure')
        if sum_error > 1e-9: reasons.append('weight_sum_failure')
        if any(t['loop_error'] > 1e-7 for t in tracks): reasons.append('loop_failure')
        if any(t['failed_ticks'] for t in tracks): reasons.append('motion_envelope_geometry_failure')
        row.update(status='blocked' if reasons else 'candidate_requires_review',
                   reason_codes=reasons or ['runtime_and_alpha_contact_required'], bone_ids=list(ids),
                   setup_vertices=deepcopy(mesh['vertices_xy']), triangles=deepcopy(mesh['triangles']),
                   weights=deepcopy(mesh['weights']), tracks=tracks, setup_error=setup_error,
                   weight_sum_error=sum_error, motion_envelope=dict(
                       geometry_pass=not any(t['failed_ticks'] for t in tracks),
                       alpha_contact_status='not_evaluated', full_angle_volume_proven=False,
                       combined_sampling='same_and_opposed_synchronized_sine'))
    return dict(schema=SCHEMA, profile=PROFILE, project_id=source['project_id'],
                source_sha256=canonical_sha256(source), draft_sha256=canonical_sha256(draft),
                skeleton_sha256=canonical_sha256(skeleton), records=rows, authority='none',
                production_authorized=False, runtime_status='not_evaluated', corrective_status='not_applied')
