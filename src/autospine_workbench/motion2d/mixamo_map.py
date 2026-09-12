"""Explicit Mixamo-name BVH mapping; no character-specific target rules."""
from ..bvh_map_validation import require_bvh_map
from ..motion_roles import CANONICAL_BONE_ROLE_ITEMS


def build_map(bvh, *, clip_id, reference_length, screen_x, screen_y, depth,
              prefix='', contact=None):
    """Map declared names and validate ancestry. Contact values use BVH units.

    Hip/clavicle lateral offsets are omitted: these are not projected limb bends.
    No loop or lock authority is inferred from a walking file name.
    """
    pairs = {
        'root': ('Hips', 'Spine'),
        'spine.lower': ('Spine', 'Spine1'),
        'spine.upper': ('Spine1', 'Spine2'),
        'neck': ('Neck', 'Head'),
        'arm.upper.left': ('LeftArm', 'LeftForeArm'),
        'arm.lower.left': ('LeftForeArm', 'LeftHand'),
        'leg.upper.left': ('LeftUpLeg', 'LeftLeg'),
        'leg.lower.left': ('LeftLeg', 'LeftFoot'),
        'arm.upper.right': ('RightArm', 'RightForeArm'),
        'arm.lower.right': ('RightForeArm', 'RightHand'),
        'leg.upper.right': ('RightUpLeg', 'RightLeg'),
        'leg.lower.right': ('RightLeg', 'RightFoot'),
    }
    rows = []
    for role, _ in CANONICAL_BONE_ROLE_ITEMS:
        pair = pairs.get(role.removeprefix('humanoid.'))
        if pair:
            joint, aim = pair
            rows.append(dict(role=role, joint_name=prefix+joint,
                             aim=dict(kind='joint', joint_name=prefix+aim),
                             rotation_policy='projected_setup_local_delta'))
    contacts = dict(enabled=False, mode='annotation_only', interval='half_open')
    if contact is not None:
        if set(contact) != {'floor', 'height', 'speed', 'minimum_frames', 'gap_frames'}:
            raise ValueError('mixamo_contact_parameters_required')
        contacts.update(enabled=True,
                        feet=[dict(limb='leg.'+side, foot_joint_name=prefix+name+'ToeBase')
                              for side, name in [('left', 'Left'), ('right', 'Right')]],
                        floor_height_source_units=contact['floor'],
                        height_threshold_source_units=contact['height'],
                        speed_threshold_source_units_per_second=contact['speed'],
                        minimum_frames=contact['minimum_frames'], gap_frames=contact['gap_frames'],
                        height_policy='absolute_signed_basis_screen_y_distance_to_floor',
                        speed_policy='source_world_3d_euclidean')
    result = dict(format='autospine-bvh-map', format_version=1,
                  map_id='mixamo-declared-body-v1', clip=dict(clip_id=clip_id, loop=False),
                  basis=dict(screen_x=screen_x, screen_y=screen_y, depth=depth,
                             rotation_convention='bvh_declared_channel_postmultiply'),
                  root=dict(joint_name=prefix+'Hips', reference_length_source_units=reference_length,
                            translation_policy='projected_frame0_delta_normalized_reference_length'),
                  bones=rows, contact=contacts)
    require_bvh_map(result, bvh=bvh)
    return result
