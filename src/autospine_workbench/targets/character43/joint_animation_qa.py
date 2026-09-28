"""M5 checks keep intentional facial compression separate from body deformation."""
from copy import deepcopy
import math
import re

from .affine_pose import sample


def _compression_limit(row, face_report, source_geometry):
    channels = (face_report or {}).get('channels', {})
    channel = channels.get(row['slot'])
    if not channel:
        return None, 'explicit_face_channel_missing'
    template = next((v for v in (face_report or {}).get('generated_templates', [])
                     if v.get('slot') == row['slot']), None)
    baseline_slot = template['parent_slot'] if template else row['slot']
    baseline = next((v for v in (source_geometry or {}).get('records', [])
                     if v.get('slot') == baseline_slot and v.get('animation') == row.get('animation')), None)
    if not baseline or not baseline.get('passed') or baseline.get('inversion_samples', 0):
        return None, 'original_face_geometry_not_verified'
    try:
        original = float(baseline['min_area_ratio'])
        factors = [float(channel[k]) for k in ('min_scale_x', 'min_scale_y')]
        # The template inherits its source mouth helper's width/turn control.
        if template:
            parent = channels[baseline_slot]
            factors.extend(float(parent[k]) for k in ('min_scale_x', 'min_scale_y'))
        if any(not math.isfinite(v) or v <= 0 for v in [original, *factors]):
            return None, 'face_scale_bound_invalid'
    except (KeyError, ValueError, TypeError):
        return None, 'face_scale_bound_invalid'
    floor = original*math.prod(factors)
    return dict(min_area_ratio=floor, baseline_slot=baseline_slot,
                baseline_min_area_ratio=original, controlled_scale_factors=factors,
                tolerance=max(1e-8, floor*1e-6),
                scope='verified_original_face_area_times_explicit_positive_channel_scales'), None


def geometry_report(raw, face_inventory, face_enabled, *, face_report=None, source_geometry=None):
    report = deepcopy(raw)
    # Only explicit face parts may compress. An inverted triangle is never exempt.
    roles = {row['slot']: row['role'] for row in face_inventory.get('parts', [])}
    compressible = {'eye.white', 'eye.iris', 'eye.lash', 'mouth',
                    'face.eye.white', 'face.eye.iris', 'face.eye.lash', 'face.mouth',
                    'eyewhite', 'iris', 'irides', 'eyelash', 'eyelashes', 'white', 'lash'}
    for row in report['records']:
        row['generic_geometry_passed'] = row['passed']
        if face_enabled and roles.get(row['slot']) in compressible:
            limit, reason = _compression_limit(row, face_report, source_geometry)
            row['intentional_compression'] = limit is not None
            if limit is None:
                row['compression_not_applied_reason'] = reason
            else:
                row['controlled_compression_limits'] = limit
                row['passed'] = (row['min_area_ratio'] >= limit['min_area_ratio']-limit['tolerance']
                    and row['inversion_samples'] == 0 and row['max_area_ratio'] <= 2
                    and row['max_edge_stretch'] <= 2)
    report.update(profile='joint-semantic-deformation-v1',
        scope='source_verified_channel_bounded_facial_compression_and_unchanged_body_geometry_limits',
        passed=all(r['passed'] for r in report['records']))
    return report


def compare(source, result, animation, times, affected):
    """A few exact probes test preservation, dense geometry is checked separately."""
    chosen = sorted({times[0], times[-1]} | {times[round(i*(len(times)-1)/8)] for i in range(9)})
    old_names = {b['name'] for b in source['bones']}
    original_bones = {b['name']: b for b in source['bones']}
    new_bones = {b['name']: b for b in result['bones']}
    if any(new_bones.get(n) != value for n, value in original_bones.items()):
        raise ValueError('joint_animation_body_setup_changed')
    original_tracks = source['animations'][animation].get('bones', {})
    new_tracks = result['animations'][animation].get('bones', {})
    changed = {n for n in old_names if original_tracks.get(n) != new_tracks.get(n)}
    if any(not (re.fullmatch(r'.+-skirt_\d+_(upper|lower)', n) or n.startswith('cloth-')) for n in changed):
        raise ValueError('joint_animation_body_track_changed')
    maximum = 0.
    for time in chosen:
        before = sample(source, animation, time)[0]
        after = sample(result, animation, time)[0]
        for slot, points in before.items():
            if slot in affected:
                continue
            if len(after[slot]) != len(points):
                raise ValueError('joint_animation_unrelated_mesh_changed')
            maximum = max(maximum, max((math.dist(a, b) for a, b in zip(points, after[slot])), default=0))
    if maximum > 1e-6:
        raise ValueError('joint_animation_unrelated_vertices_changed')
    return dict(passed=True, samples=len(chosen), untouched_max_error_px=maximum,
                unchanged_body_setup=True, changed_existing_aux_tracks=sorted(changed))
