"""Apply source projection ratios as world-axis length candidates, parent compensated."""
from copy import deepcopy
import math
from ...bvh_fk import project_bvh_frames
from .affine_pose import matrices
from .motionir_candidate import ROLES


def build(document, name, bvh, mapping, *, time_range=None):
    from .motion_clip import selected_ratios
    projected = project_bvh_frames(bvh, mapping)
    rows = [r for r in mapping['bones'] if r['role'].startswith(('humanoid.leg.', 'humanoid.arm.'))]
    ratios = {}; summary = []
    for row in rows:
        if row['aim']['kind'] != 'joint':
            raise ValueError('character_length_joint_aim_required')
        values = []
        for frame in projected.frames:
            joints = dict(frame.joints)
            a, b = joints[row['joint_name']], joints[row['aim']['joint_name']]
            world = math.dist(a.world_xyz, b.world_xyz)
            visible = math.dist(a.screen_xy, b.screen_xy)
            values.append(visible/world if world > 1e-8 else 0.)
        values, times = selected_ratios(values, [frame.tick/1_000_000 for frame in projected.frames], time_range)
        bone = ROLES[row['role']]
        ratios[bone] = values
        summary.append(dict(role=row['role'], bone=bone, min_ratio=min(values), max_ratio=max(values)))
    return apply_ratios(document, name, ratios, summary,
                        times,
                        projected.source_sha256, projected.map_sha256)


def apply_ratios(document, name, ratios, summary, times, source_sha256, map_sha256):
    """Shared axial scaling after source-specific, validated 3D projection."""
    result = deepcopy(document)
    tracks = result['animations'][name]['bones']
    if any(tracks.get(b, {}).get('scale') for b in ratios):
        raise ValueError('character_length_scale_already_present')
    baseline = matrices(document, name, 0)
    for index, time in enumerate(times):
        for bone in result['bones']:
            key = bone['name']
            if key not in ratios:
                continue
            current = matrices(result, name, time)[key]
            desired = math.hypot(baseline[key][0], baseline[key][2])*ratios[key][index]
            keys = tracks.setdefault(key, {}).setdefault('scale', [])
            previous = keys[-1]['x'] if keys else 1.
            value = previous*desired/math.hypot(current[0], current[2])
            keys.append(dict(time=time, x=value, y=1.))
            actual = matrices(result, name, time)[key]
            # Preserve perpendicular thickness, rather than inheriting a parent's
            # axial shortening as an unintended compression of this bone's width.
            base = baseline[key]
            base_area = base[0]*base[3]-base[1]*base[2]
            area = actual[0]*actual[3]-actual[1]*actual[2]
            if base_area <= 0 or area <= 0:
                raise ValueError('character_length_orientation_invalid')
            keys[-1]['y'] = base_area*ratios[key][index]/area
            actual = matrices(result, name, time)[key]
            if abs(math.hypot(actual[0], actual[2])-desired) > 1e-7:
                raise ValueError('character_length_world_axis_mismatch')
    return result, dict(profile='projected-world-axis-width-v1', authority='none',
                        status='preview_only', source_sha256=source_sha256,
                        map_sha256=map_sha256, ratios=summary,
                        limitation='fixed_texture_depth_order_and_visibility_unresolved')
