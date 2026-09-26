"""Remove inherited transverse shear from selected limb skins, not bone motion.

The axial projection and signed area of every individual influence stay intact.
Existing local corrections are added unchanged. Mixed weights still require QA.
"""
from copy import deepcopy
import math

from .affine_pose import matrices
from ..spine43.continuous_pose import interpolate

PROFILE = 'limb-transverse-frame-compensation-v1-experiment'


def _frame(matrix):
    a, b, c, d = matrix[:4]
    length2 = a*a+c*c
    determinant = a*d-b*c
    if (not all(math.isfinite(x) for x in matrix) or
            length2 <= 1e-12 or determinant <= 1e-10):
        raise ValueError('limb_transverse_frame_degenerate')
    return (a*b+c*d)/length2, math.sqrt(length2), determinant


def _entries(mesh, bones):
    if mesh.get('type') != 'mesh' or len(mesh['vertices']) == len(mesh['uvs']):
        raise ValueError('limb_transverse_weighted_mesh_required')
    data = mesh['vertices']; rows = []; i = 0
    while i < len(data):
        count = data[i]; i += 1
        if type(count) is not int or count < 1 or i+4*count > len(data):
            raise ValueError('limb_transverse_weights_invalid')
        row = []
        for _ in range(count):
            index, x, y, weight = data[i:i+4]; i += 4
            if (type(index) is not int or not 0 <= index < len(bones) or
                    not all(math.isfinite(v) for v in (x, y, weight)) or weight < 0):
                raise ValueError('limb_transverse_weights_invalid')
            row.append((bones[index]['name'], y, weight))
        if abs(sum(r[2] for r in row)-1) > 1e-6:
            raise ValueError('limb_transverse_weights_invalid')
        rows.append(row)
    if len(rows)*2 != len(mesh['uvs']):
        raise ValueError('limb_transverse_vertex_inventory')
    return rows


def _chain(rows):
    used = {name for row in rows for name, _, weight in row if weight > 0}
    for side in ('l', 'r'):
        for parts in (('thigh', 'calf', 'foot'), ('upperarm', 'forearm', 'hand')):
            allowed = {p+'_'+side for p in parts}
            if used and used <= allowed:
                return used
    raise ValueError('limb_transverse_single_limb_required')


def prepare(document, name, slots, maximum_keys=2049):
    """Read-only structural preflight shared with the actual bake."""
    if (not slots or len(slots) != len(set(slots)) or
            type(maximum_keys) is not int or not 3 <= maximum_keys <= 2049):
        raise ValueError('limb_transverse_options_invalid')
    if len(document['skins']) != 1 or document['skins'][0]['name'] != 'default':
        raise ValueError('limb_transverse_skin_unsupported')
    animation = document['animations'][name]
    if (animation.get('deform') or set(animation.get('attachments', {}))-{'default'} or
            any('attachment' in t for t in animation.get('slots', {}).values())):
        raise ValueError('limb_transverse_timeline_unsupported')
    channels = list(animation.get('bones', {}).values())
    original = animation.get('attachments', {}).get('default', {})
    rows = {}; previous = {}; used = set()
    for slot in slots:
        choices = document['skins'][0]['attachments'][slot]
        if set(choices) != {slot}:
            raise ValueError('limb_transverse_attachment_ambiguous')
        rows[slot] = _entries(choices[slot], document['bones'])
        used |= _chain(rows[slot])
        props = original.get(slot, {}).get(slot, {})
        if set(props)-{'deform'}:
            raise ValueError('limb_transverse_timeline_unsupported')
        previous[slot] = props.get('deform', [])
        if any('offset' in k for k in previous[slot]):
            raise ValueError('limb_transverse_dense_deform_required')
        channels.append(props)
    if any('curve' in k for tracks in channels for keys in tracks.values() for k in keys):
        raise ValueError('limb_transverse_linear_required')
    times = {k.get('time', 0) for tracks in channels for keys in tracks.values() for k in keys}
    if len(times) < 2 or min(times) != 0 or any(not math.isfinite(t) for t in times):
        raise ValueError('limb_transverse_times_invalid')
    if len(times) > maximum_keys:
        raise ValueError('limb_transverse_key_limit')
    rest = deepcopy(document); rest['animations'][name] = {'bones': {}}
    baseline = {n: _frame(m) for n, m in matrices(rest, name, 0).items() if n in used}
    return rows, previous, used, times, baseline


def build(document, name, slots, *, tolerance_px=.05, maximum_keys=2049, on_progress=None):
    """Bake additive rest-surface compensation with quarter-interval error checks.

    Axial shortening is deliberately not clamped and the geometry gate is not
    changed. This planar frame convention does not reconstruct 3D surface twist.
    """
    if not math.isfinite(tolerance_px) or not 0 < tolerance_px <= .1:
        raise ValueError('limb_transverse_options_invalid')
    rows, previous, used, times, baseline = prepare(document, name, slots, maximum_keys)
    cache = {}

    def at(time):
        if time not in cache:
            if on_progress and len(cache) % 64 == 0:
                on_progress(dict(stage='compensate_transverse', index=len(cache)))
            transforms = matrices(document, name, time)
            frames = {n: _frame(transforms[n]) for n in used}
            offsets = {}; maximum = {}
            for slot in slots:
                old = interpolate(previous[slot], time, 'vertices') if previous[slot] else []
                count = 2*sum(len(r) for r in rows[slot])
                if old and (len(old) != count or not all(math.isfinite(v) for v in old)):
                    raise ValueError('limb_transverse_deform_inventory')
                values = []; j = 0; peak = 0.
                for row in rows[slot]:
                    dx = dy = 0.
                    for bone, y, weight in row:
                        shift = (baseline[bone][0]-frames[bone][0])*y if weight > 0 else 0.
                        px, py = old[j:j+2] if old else (0., 0.)
                        values.extend((px+shift, py)); j += 2
                        if weight > 0:
                            a, _, c, _, _, _ = transforms[bone]
                            dx += weight*a*shift; dy += weight*c*shift
                    peak = max(peak, math.hypot(dx, dy))
                offsets[slot] = values; maximum[slot] = peak
            cache[time] = (offsets, transforms, frames, maximum)
        return cache[time]

    def error(time, left, right):
        exact, transforms, _, _ = at(time); u = (time-left)/(right-left)
        start = at(left)[0]; end = at(right)[0]; worst = 0.
        for slot in slots:
            j = 0
            for row in rows[slot]:
                dx = dy = 0.
                for bone, _, weight in row:
                    x = (1-u)*start[slot][j]+u*end[slot][j]-exact[slot][j]
                    y = (1-u)*start[slot][j+1]+u*end[slot][j+1]-exact[slot][j+1]; j += 2
                    if weight > 0:
                        a, b, c, d, _, _ = transforms[bone]
                        dx += weight*(a*x+b*y); dy += weight*(c*x+d*y)
                worst = max(worst, math.hypot(dx, dy))
        return worst

    for iteration in range(9):
        ordered = sorted(times); extra = set(); maximum_error = 0.
        for left, right in zip(ordered, ordered[1:]):
            for u in (.25, .5, .75):
                time = left+(right-left)*u; value = error(time, left, right)
                maximum_error = max(maximum_error, value)
                if value > tolerance_px:
                    extra.add(time)
        if not extra:
            break
        if iteration == 8 or len(times | extra) > maximum_keys:
            raise ValueError('limb_transverse_interpolation_unresolved')
        times |= extra
    result = deepcopy(document)
    target = result['animations'][name].setdefault('attachments', {}).setdefault('default', {})
    for slot in slots:
        target.setdefault(slot, {}).setdefault(slot, {})['deform'] = [
            dict(time=t, vertices=at(t)[0][slot]) for t in sorted(times)]
    report = dict(profile=PROFILE, authority='none', selected=False, production_authorized=False,
        status='candidate_requires_validation', slots=list(slots), bones=sorted(used),
        sample_count=len(times), validation_sample_count=len(cache),
        maximum_interpolation_error_px=maximum_error, tolerance_px=tolerance_px,
        maximum_displacement_px={s: max(v[3][s] for v in cache.values()) for s in slots},
        scope='sampled_planar_transverse_compensation_not_surface_or_visual_acceptance',
        invariants=['bone_tracks_unchanged', 'weights_uv_topology_unchanged',
                    'existing_corrective_offsets_retained', 'axial_projection_not_clamped'],
        limitations=['mixed_weight_geometry_requires_recheck', 'depth_and_contact_require_recheck',
                     'no_side_back_artwork_or_3d_twist_reconstruction', 'sampled_interpolation_only'])
    return result, report
