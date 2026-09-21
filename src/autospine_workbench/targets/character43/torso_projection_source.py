"""Observed shoulder/pelvis plane shape, removing roll already handled by MotionIR."""
import json
import math

from .oblique_source import _basis
from .oblique_motion import project

PROFILE = 'source-torso-plane-shape-v1-experiment'


def anchors(bundle, yaw=0):
    mapping = json.loads((bundle.path/'map.json').read_bytes())
    roles = {r['role']: r['joint_name'] for r in mapping['bones']}
    names = [roles['humanoid.arm.upper.left'], roles['humanoid.arm.upper.right'], mapping['root']['joint_name']]
    if bundle.source_kind == 'bvh':
        from ...bvh_parser import parse_bvh
        from ...bvh_fk import _world_matrices, _origin, bvh_frame_ticks
        bvh = parse_bvh(bundle.raw_bvh); lookup = {j.name: i for i, j in enumerate(bvh.joints)}
        values = []
        for frame in bvh.frames:
            world = _world_matrices(bvh, frame)
            values.append([_origin(world[lookup[n]]) for n in names])
        ticks = bvh_frame_ticks(bvh)
    elif bundle.source_kind == 'kimodo_npz':
        from ...kimodo_npz_reader import decode_kimodo_npz
        from ...kimodo_npz_consistency import validate_kimodo_consistency
        from ...kimodo_soma77 import SOMA77_INDEX_BY_NAME
        from ...kimodo_npz_projection import kimodo_frame_ticks
        source = bundle.kimodo_source
        positions = validate_kimodo_consistency(decode_kimodo_npz(bundle.raw_npz, source), source).positions
        values = [[frame[SOMA77_INDEX_BY_NAME[n]] for n in names] for frame in positions]
        ticks = kimodo_frame_ticks(source)
    else:
        raise ValueError('torso_source_unsupported')
    return [[project(_basis(p, mapping['basis']), yaw) for p in frame] for frame in values], ticks


def shapes(frames, times):
    if (len(frames) != len(times) or len(times) < 2
            or any(not math.isfinite(t) for t in times)
            or any(b <= a for a,b in zip(times,times[1:]))):
        raise ValueError('torso_samples_invalid')
    measurements = []
    for left,right,pelvis in frames:
        if any(len(p)!=3 or any(not math.isfinite(v) for v in p) for p in (left,right,pelvis)):
            raise ValueError('torso_anchors_invalid')
        # Convert screen Y-down to target Y-up before constructing the local plane.
        u = (right[0]-left[0], left[1]-right[1])
        v = ((left[0]+right[0])/2-pelvis[0], pelvis[1]-(left[1]+right[1])/2)
        height = math.hypot(*v); width3d = math.dist(left,right)
        if height <= 1e-10 or width3d <= 1e-10:
            raise ValueError('torso_anchor_axis_degenerate')
        width = (v[0]*u[1]-v[1]*u[0])/height
        along = (v[0]*u[0]+v[1]*u[1])/height
        measurements.append((height,width,along,abs(width)/width3d))
    h0,w0,q0,visible0 = measurements[0]
    if visible0 < .2:
        raise ValueError('torso_initial_view_degenerate')
    rows = []
    for time,(h,w,q,visible) in zip(times,measurements):
        longitudinal, transverse = h/h0,w/w0
        shear = (q-longitudinal*q0)/w0
        reasons = []
        if visible < .2: reasons.append('torso_side_view_degenerate')
        if transverse <= 0: reasons.append('torso_back_view_requires_artwork')
        elif not .5 <= transverse <= 1.5: reasons.append('torso_width_outside_candidate_range')
        if not .75 <= longitudinal <= 1.25: reasons.append('torso_height_outside_candidate_range')
        if abs(shear) > .5: reasons.append('torso_shear_outside_candidate_range')
        rows.append(dict(time=time, longitudinal=longitudinal, transverse=transverse,
                         shear=shear, visibility=visible, reasons=reasons))
    return dict(profile=PROFILE, records=rows, authority='none',
        limits=dict(width_ratio=[.5,1.5],height_ratio=[.75,1.25],maximum_shear=.5,minimum_visibility=.2),
        assumption='planar_torso_shape_without_hidden_artwork_or_axial_twist')
