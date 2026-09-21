"""Torso depth anchors at exact source keys of the compensated visual bake."""
import math

from .affine_pose import matrices
from .cloth_depth_plane import fit
from .torso_projection_candidate import PROFILE, transformed


class WarpedPlane:
    def __init__(self, receipt, expected_source):
        if receipt.get('profile') != PROFILE or receipt.get('applied') is not True:
            raise ValueError('depth_torso_bake_required')
        if receipt.get('source') != expected_source:
            raise ValueError('depth_torso_source_mismatch')
        rows = expected_source['records']
        if not rows or any(r['reasons'] for r in rows):
            raise ValueError('depth_torso_shape_unsupported')
        self.rows = {r['time']: r for r in rows}
        if len(self.rows) != len(rows):
            raise ValueError('depth_torso_duplicate_time')

    def __call__(self, document, animation, time, sampler, source_tick):
        # Source keys are explicitly included in the deform bake. At intermediate
        # times Spine interpolates baked offsets, not the ideal shape transform.
        if not math.isfinite(time) or time not in self.rows:
            raise ValueError('depth_torso_between_bake_source_keys_unsupported')
        r = self.rows[time]
        pose = transformed(document, matrices(document, animation, time),
                           [r['longitudinal'], r['shear'], r['transverse']])
        points = {n: list(pose[n][4:6]) for n in
                  ('upperarm_l', 'upperarm_r', 'pelvis') if n in pose}
        result = fit(points, sampler.torso_anchors(source_tick))
        return dict(result, anchor_profile='compensated-torso-source-key-origins-v1',
                    time=time, source_tick=source_tick,
                    anchor_scope='visual_bake_virtual_origins_not_unchanged_bone_guides')
