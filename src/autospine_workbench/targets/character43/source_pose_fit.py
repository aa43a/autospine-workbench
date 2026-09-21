"""Experimental absolute limb-direction fit; never treats frame zero as rest."""
from copy import deepcopy
import math

from ...resolved_project import canonical_sha256
from .affine_pose import matrices
from .motionir_candidate import ROLES
from .oblique_motion import project

PROFILE = 'source-absolute-limb-direction-v1'


def fit(document, name, vectors, times, *, yaw=0, project_lengths=False):
    """Fit projected directions through each animated parent's inverse matrix.

    This isolates pose calibration from mesh correction. Near-camera directions
    remain explicitly unreliable, even when the numeric fit is exact.
    """
    if (len(times) < 2 or any(not math.isfinite(t) or t < 0 for t in times)
            or any(b <= a for a, b in zip(times, times[1:]))):
        raise ValueError('source_pose_times_invalid')
    if not math.isfinite(yaw) or not -90 <= yaw <= 90:
        raise ValueError('source_pose_yaw_invalid')
    animation = document['animations'][name]
    if animation.get('attachments') or animation.get('deform'):
        raise ValueError('source_pose_fit_requires_uncorrected_mesh')
    selected = {ROLES[r]: (r, values) for r, values in vectors.items()
                if r.startswith(('humanoid.arm.', 'humanoid.leg.')) and r in ROLES}
    if not selected:
        raise ValueError('source_pose_limbs_missing')
    if type(project_lengths) is not bool:
        raise ValueError('source_pose_length_mode_invalid')
    if project_lengths and any(animation.get('bones', {}).get(b, {}).get('scale') for b in selected):
        raise ValueError('source_pose_existing_scale')
    bones = {b['name']: b for b in document['bones']}
    if set(selected) - set(bones):
        raise ValueError('source_pose_target_missing')
    for bone in document['bones']:
        if bone.get('inherit', 'normal') != 'normal' or bone.get('shearX', 0) or bone.get('shearY', 0):
            raise ValueError('source_pose_transform_unsupported')
    for _, values in selected.values():
        if len(values) != len(times) or any(len(v) != 3 or not all(math.isfinite(x) for x in v) for v in values):
            raise ValueError('source_pose_vectors_invalid')
        if any(math.hypot(*project(v, yaw)[:2]) <= 1e-10 for v in values):
            raise ValueError('source_pose_direction_unobservable')
    result = deepcopy(document)
    setup = deepcopy(document)
    setup['animations'][name] = {'bones': {}}
    rest = matrices(setup, name, 0)
    tracks = result['animations'][name].setdefault('bones', {})
    for bone in selected:
        tracks.setdefault(bone, {})['rotate'] = []
        if project_lengths:
            tracks[bone]['scale'] = []
    records = {bone: dict(role=role, bone=bone, unreliable_frames=[],
                         maximum_direction_error_deg=0., first_frame_rotation_deg=None,
                         maximum_axis_length_error=0.)
               for bone, (role, _) in selected.items()}
    for index, time in enumerate(times):
        # Document bone order is parent first (also required by affine_pose).
        for bone in result['bones']:
            key = bone['name']
            if key not in selected:
                continue
            vector = selected[key][1][index]
            x, y, _ = project(vector, yaw)
            # Source basis is screen-down; Spine is screen-up.
            y = -y
            parent = matrices(result, name, time).get(bone.get('parent'), (1, 0, 0, 1, 0, 0))
            a, b, c, d = parent[:4]
            determinant = a*d-b*c
            if determinant <= 1e-10:
                raise ValueError('source_pose_parent_singular')
            local_x, local_y = (d*x-b*y)/determinant, (-c*x+a*y)/determinant
            value = math.degrees(math.atan2(local_y, local_x))-bone.get('rotation', 0)
            keys = tracks[key]['rotate']
            if keys:
                value = keys[-1]['value']+(value-keys[-1]['value']+180) % 360-180
            keys.append(dict(time=time, value=value))
            row = records[key]
            if index == 0:
                row['first_frame_rotation_deg'] = value
            visibility = math.hypot(x, y)/math.sqrt(sum(v*v for v in vector))
            if visibility < .2:
                row['unreliable_frames'].append(dict(frame=index, time=time, visibility=visibility))
            if project_lengths:
                # Preserve the rest perpendicular thickness while shortening the
                # world axis. Compensate the actual affine parent, not just its angle.
                scale_keys = tracks[key]['scale']
                scale_keys.append(dict(time=time, x=1., y=1.))
                current = matrices(result, name, time)[key]
                base = rest[key]
                desired = math.hypot(base[0], base[2])*visibility
                scale_keys[-1]['x'] = desired/math.hypot(current[0], current[2])
                current = matrices(result, name, time)[key]
                scale_keys[-1]['y'] = (base[0]*base[3]-base[1]*base[2])*visibility/(current[0]*current[3]-current[1]*current[2])
                current = matrices(result, name, time)[key]
                row['maximum_axis_length_error'] = max(row['maximum_axis_length_error'], abs(math.hypot(current[0], current[2])-desired))
            world = matrices(result, name, time)[key]
            error = abs((math.degrees(math.atan2(world[2], world[0])-math.atan2(y, x))+180) % 360-180)
            row['maximum_direction_error_deg'] = max(row['maximum_direction_error_deg'], error)
    return result, dict(profile=PROFILE if not project_lengths else 'source-absolute-limb-projection-v1', authority='none', selected=False,
        input_sha256=canonical_sha256(dict(document=document, vectors=vectors, times=times, yaw=yaw, project_lengths=project_lengths)),
        output_sha256=canonical_sha256(result), records=list(records.values()),
        limitations=['direction_fit_not_joint_position_or_silhouette_fit',
                     'unreliable_projection_requires_3d_bend_plane_resolution',
                     'requires_new_mesh_contact_depth_and_runtime_checks'])
