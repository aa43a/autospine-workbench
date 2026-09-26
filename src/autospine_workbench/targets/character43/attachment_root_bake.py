"""Independent deform candidate: translate declared garment roots with chest warp."""
from copy import deepcopy
import math

from .affine_pose import matrices
from .attachment_root_transport import displacements
from .torso_projection_candidate import transformed, inverse
from .runtime_storage_reference import f32
from ..spine43.continuous_pose import interpolate


def build(document, animation, torso, roots, times, on_progress=None):
    if torso.get('applied') is not True:
        raise ValueError('attachment_transport_requires_baked_torso')
    if torso.get('profile') not in ('torso-plane-compensated-deform-v1-experiment',
            'reference-torso-plane-compensated-deform-v1-experiment'):
        raise ValueError('attachment_transport_profile_unsupported')
    rows = torso['source']['records']
    if (len(rows) < 2 or rows[0]['time'] != 0 or rows[-1]['time'] <= 0
            or any(not math.isfinite(r[k]) for r in rows for k in
                   ('time', 'longitudinal', 'shear', 'transverse'))
            or any(b['time'] <= a['time'] for a, b in zip(rows, rows[1:]))):
        raise ValueError('attachment_transport_shape_invalid')
    if any(r.get('reasons') or not (.75 <= r['longitudinal'] <= 1.25
            and .5 <= r['transverse'] <= 1.5 and abs(r['shear']) <= .5) for r in rows):
        raise ValueError('attachment_transport_source_limits')
    if (not times or len(times) > 4097 or times != sorted(set(times))
            or times[0] != 0 or any(not math.isfinite(t) or t < 0 for t in times)
            or abs(times[-1]-rows[-1]['time']) > 1e-5):
        raise ValueError('attachment_transport_times_invalid')
    if len(document['skins']) != 1 or document['skins'][0]['name'] != 'default':
        raise ValueError('attachment_transport_skin_unsupported')
    original = document['animations'][animation]
    if original.get('deform'):
        raise ValueError('attachment_transport_legacy_deform_unsupported')
    shapes = [dict(time=r['time'], vertices=[r['longitudinal'], r['shear'], r['transverse']]) for r in rows]
    keys = sorted({f32(time) for time in times})
    result = deepcopy(document)
    tracks = result['animations'][animation].setdefault('attachments', {}).setdefault('default', {})
    changes = {}; maximum = 0.
    for step, time in enumerate(keys):
        if on_progress and step % 32 == 0:
            on_progress(dict(stage='garment_root_transport', index=step, total=len(keys)))
        baseline = matrices(document, animation, time)
        warped = transformed(document, baseline, interpolate(shapes, time, 'vertices'))
        shifts = displacements(document['bones'], baseline, warped, 'chest', roots)
        for slot, choices in document['skins'][0]['attachments'].items():
            if set(choices) != {slot}:
                raise ValueError('attachment_transport_attachment_choice_unsupported')
            mesh = choices[slot]; data = mesh['vertices']
            if mesh.get('type') != 'mesh' or len(data) == len(mesh['uvs']):
                raise ValueError('attachment_transport_weighted_mesh_required')
            prior_keys = original.get('attachments', {}).get('default', {}).get(slot, {}).get(slot, {}).get('deform')
            previous = interpolate(prior_keys, time, 'vertices') if prior_keys else []
            values = []; i = j = 0; touched = False
            while i < len(data):
                count = data[i]; i += 1
                for _ in range(count):
                    index, _, _, weight = data[i:i+4]; i += 4
                    bone = document['bones'][index]['name']
                    px, py = previous[j:j+2] if previous else (0., 0.); j += 2
                    if bone in shifts and weight > 0:
                        dx, dy = shifts[bone]; matrix = inverse(baseline[bone])
                        px += matrix[0]*dx+matrix[1]*dy; py += matrix[2]*dx+matrix[3]*dy
                        maximum = max(maximum, math.hypot(dx, dy)); touched = True
                    values.extend((px, py))
            if touched:
                changes.setdefault(slot, []).append(dict(time=time, vertices=values))
    if not changes:
        raise ValueError('attachment_transport_no_affected_vertices')
    for slot, values in changes.items():
        # Keep all other attachment properties, including future color/sequence channels.
        tracks.setdefault(slot, {}).setdefault(slot, {})['deform'] = values
    return result, dict(profile='declared-garment-root-translation-v1-experiment',
        roots=sorted(roots), rows=[dict(slot=s) for s in sorted(changes)],
        maximum_root_shift_px=maximum, original_reference_samples=len(times), key_samples=len(keys),
        time_policy='recompute_at_distinct_runtime_float32_times_preserve_original_qa_samples',
        authority='none', selected=False, scope='root_translation_requires_all_target_checks')
