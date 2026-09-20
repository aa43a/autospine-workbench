"""Conservative source-world ankle support hypotheses, never source labels."""
from copy import deepcopy
import math

from ..bvh_contact import detect_bvh_contacts
from ..bvh_fk import project_bvh_frames
from ..bvh_map_validation import bvh_map_sha256, require_bvh_map

PROFILE = 'bvh-low-stationary-ankle-v1'
UP_PROFILE = 'bvh-declared-up-stationary-ankle-v2'


def estimate_plane(points, axis, reference_length):
    """Low observed ankle level is a proxy; it is not an observed floor."""
    if axis not in ('+X', '-X', '+Y', '-Y', '+Z', '-Z'):
        raise ValueError('contact_candidate_axis_invalid')
    if not math.isfinite(reference_length) or reference_length <= 0:
        raise ValueError('contact_candidate_scale_invalid')
    if not points or any(len(p) != 3 or any(not math.isfinite(v) for v in p) for p in points):
        raise ValueError('contact_candidate_points_invalid')
    index, sign = 'XYZ'.index(axis[1]), 1 if axis[0] == '+' else -1
    heights = sorted(sign*p[index] for p in points)
    return heights[math.floor((len(heights)-1)*.05)]


def infer(bvh, mapping, *, source_up=None):
    require_bvh_map(mapping, bvh=bvh)
    report = dict(schema='autospine.source-contact-candidate/v1', profile=UP_PROFILE if source_up else PROFILE,
        authority='none', selected=False, source_sha256=bvh.source_sha256,
        map_sha256=bvh_map_sha256(mapping), status='unavailable', markers=[],
        scope='low_stationary_ankle_hypothesis_not_floor_or_sole',
        limitations=['stationary_airborne_pose_is_not_distinguishable',
                     'moving_platform_and_treadmill_support_not_inferred'])
    if mapping['contact']['enabled']:
        report['status'] = 'existing_contact_configuration_preserved'
        return report
    if bvh.frame_count < 3 or mapping['clip']['loop']:
        report['reason'] = 'insufficient_frames_or_loop_boundary'
        return report
    roles = {r['role']: r for r in mapping['bones']}
    feet = []
    for side in ('left', 'right'):
        row = roles.get('humanoid.leg.lower.'+side)
        if not row or row['aim']['kind'] != 'joint':
            report['reason'] = 'bilateral_ankle_mapping_missing'
            return report
        feet.append(dict(limb='leg.'+side, foot_joint_name=row['aim']['joint_name']))
    projection = project_bvh_frames(bvh, mapping)
    frames = [dict(f.joints) for f in projection.frames]
    length = mapping['root']['reference_length_source_units']
    screen_y = mapping['basis']['screen_y']
    if source_up is not None and (source_up not in ('+X', '-X', '+Y', '-Y', '+Z', '-Z') or source_up[1] != screen_y[1]):
        raise ValueError('contact_source_up_not_aligned_with_screen_vertical')
    floor = estimate_plane([f[foot['foot_joint_name']].world_xyz for f in frames for foot in feet],
                           source_up or screen_y, length)
    if source_up:
        report['source_up'] = source_up
        if source_up != screen_y:
            floor = -floor
    derived = deepcopy(mapping)
    derived['contact'] = dict(enabled=True, mode='annotation_only', interval='half_open', feet=feet,
        floor_height_source_units=floor, height_threshold_source_units=.025*length,
        speed_threshold_source_units_per_second=.08*length,
        minimum_frames=max(3, math.ceil(.12/bvh.frame_time_seconds)), gap_frames=0,
        height_policy='absolute_signed_basis_screen_y_distance_to_floor',
        speed_policy='source_world_3d_euclidean')
    # Recompute a map-bound snapshot: do not relabel the original FK identity.
    markers = detect_bvh_contacts(bvh, derived, projected=project_bvh_frames(bvh, derived))
    report.update(status='candidate' if markers else 'no_stationary_support_evidence',
                  markers=[m.document for m in markers], derived_contact=derived['contact'],
                  derived_map_sha256=bvh_map_sha256(derived),
                  ticks_per_second=1_000_000, duration_ticks=projection.duration_ticks)
    return report
