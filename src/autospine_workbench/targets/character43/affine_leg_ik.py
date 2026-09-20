"""Bounded two-rotation endpoint solve with actual inherited affine scales.

Search failure is not proof of infeasibility. No scale or translation is changed.
"""
import math

from .affine_pose import matrices
from ..spine43.continuous_pose import interpolate


def _local(bone, tracks, time):
    angle = bone['rotation']
    if tracks.get('rotate'):
        angle += interpolate(tracks['rotate'], time, 'value')
    x, y = bone['x'], bone['y']
    sx, sy = bone.get('scaleX', 1), bone.get('scaleY', 1)
    for kind in ('translate', 'scale'):
        if tracks.get(kind):
            keys = [dict(time=k['time'], vertices=[k['x'], k['y']]) for k in tracks[kind]]
            u, v = interpolate(keys, time, 'vertices')
            if kind == 'translate':
                x += u; y += v
            else:
                sx *= u; sy *= v
    return angle, x, y, sx, sy


def _rotate(angle, point):
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return c*point[0]-s*point[1], s*point[0]+c*point[1]


def _delta(angle):
    return (angle+180) % 360-180


def solve(document, animation, time, upper, lower, tip, target, *, maximum_degrees=30):
    if not math.isfinite(maximum_degrees) or not 0 < maximum_degrees <= 90:
        raise ValueError('affine_ik_angle_limit_invalid')
    if len(target) != 2 or any(not math.isfinite(v) for v in target):
        raise ValueError('affine_ik_target_invalid')
    bones = {b['name']: b for b in document['bones']}
    if bones[lower].get('parent') != upper or bones[tip].get('parent') != lower:
        raise ValueError('affine_ik_direct_chain_required')
    tracks = document['animations'][animation].get('bones', {})
    if any('curve' in k for row in tracks.values() for keys in row.values() for k in keys):
        raise ValueError('affine_ik_linear_required')
    pose = matrices(document, animation, time)
    parent = bones[upper].get('parent')
    pa, pb, pc, pd, _, _ = pose[parent] if parent else (1, 0, 0, 1, 0, 0)
    det = pa*pd-pb*pc
    if abs(det) < 1e-10:
        raise ValueError('affine_ik_singular_parent')
    dx, dy = target[0]-pose[upper][4], target[1]-pose[upper][5]
    requested = ((pd*dx-pb*dy)/det, (-pc*dx+pa*dy)/det)
    distance = math.hypot(*requested)
    ua, _, _, usx, usy = _local(bones[upper], tracks.get(upper, {}), time)
    la, lx, ly, lsx, lsy = _local(bones[lower], tracks.get(lower, {}), time)
    _, tx, ty, _, _ = _local(bones[tip], tracks.get(tip, {}), time)
    distal = (tx*lsx, ty*lsy)
    # Triangle inequality gives a conservative outer reach bound even when
    # the animated thigh scale is anisotropic. Exceeding it proves too-far;
    # lying within it does not prove reachability or a bounded-angle solution.
    maximum_reach_bound = max(usx, usy)*(math.hypot(lx, ly)+math.hypot(*distal))

    def vector(angle):
        rx, ry = _rotate(angle, distal)
        return usx*(lx+rx), usy*(ly+ry)

    def residual(angle):
        return math.hypot(*vector(angle))-distance

    # Bounded 1D search in the lower rotation. Upper rotation then aligns the
    # endpoint in parent coordinates; circular world-space IK would be wrong.
    grid = [la-maximum_degrees+2*maximum_degrees*i/120 for i in range(121)]
    roots = [a for a in grid if abs(residual(a)) < 1e-8]
    for left, right in zip(grid, grid[1:]):
        fl, fr = residual(left), residual(right)
        if fl*fr >= 0:
            continue
        for _ in range(45):
            middle = (left+right)/2
            fm = residual(middle)
            if fl*fm <= 0:
                right = middle
            else:
                left, fl = middle, fm
        roots.append((left+right)/2)
    candidates = []
    for angle in roots:
        v = vector(angle)
        rotation = math.degrees(math.atan2(requested[1], requested[0])-math.atan2(v[1], v[0]))
        du, dl = _delta(rotation-ua), angle-la
        if abs(du) > maximum_degrees+1e-8:
            continue
        rotated = _rotate(ua+du, v)
        error = math.hypot(pa*(rotated[0]-requested[0])+pb*(rotated[1]-requested[1]),
                           pc*(rotated[0]-requested[0])+pd*(rotated[1]-requested[1]))
        candidates.append(dict(upper_delta_degrees=du, lower_delta_degrees=dl, endpoint_error_px=error))
    best = min(candidates, key=lambda c: c['upper_delta_degrees']**2+c['lower_delta_degrees']**2, default=None)
    return dict(profile='bounded-affine-leg-rotation-v1', selected=False,
                status='candidate' if best else 'no_bounded_solution_found', solution=best,
                parent_space_distance=distance, maximum_reach_bound=maximum_reach_bound,
                exceeds_outer_reach_bound=distance > maximum_reach_bound+1e-8,
                maximum_degrees=maximum_degrees, scope='endpoint_only_not_mesh_or_runtime_validation')
