"""Source ankle trajectories in the selected camera; no stationary-foot inference."""
import math
from .oblique_source import _basis
from .oblique_motion import project


def extract(bundle, yaw=0):
    if not math.isfinite(yaw):
        raise ValueError('ankle_source_yaw_invalid')
    if bundle.source_kind == 'bvh':
        from ...bvh_parser import parse_bvh
        from ...bvh_fk import _world_matrices, _origin, bvh_frame_ticks
        mapping = bundle.bvh_map
        roles = {r['role']: r for r in mapping['bones']}
        aims = [roles['humanoid.leg.lower.'+s]['aim'] for s in ('left', 'right')]
        if any(a['kind'] != 'joint' for a in aims):
            raise ValueError('ankle_source_joint_aim_required')
        names = [a['joint_name'] for a in aims]
        source = parse_bvh(bundle.raw_bvh)
        lookup = {j.name: i for i, j in enumerate(source.joints)}
        points = []
        for frame in source.frames:
            world = _world_matrices(source, frame)
            points.append([_origin(world[lookup[n]]) for n in names])
        ticks = bvh_frame_ticks(source)
        reference = mapping['root']['reference_length_source_units']
    elif bundle.source_kind == 'kimodo_npz':
        from ...kimodo_npz_reader import decode_kimodo_npz
        from ...kimodo_npz_consistency import validate_kimodo_consistency
        from ...kimodo_soma77 import SOMA77_INDEX_BY_NAME
        from ...kimodo_npz_projection import kimodo_frame_ticks
        mapping = bundle.kimodo_map
        roles = {r['role']: r for r in mapping['bones']}
        names = [roles['humanoid.leg.lower.'+s]['aim_joint_name'] for s in ('left', 'right')]
        source = bundle.kimodo_source
        decoded = validate_kimodo_consistency(decode_kimodo_npz(bundle.raw_npz, source), source)
        points = [[frame[SOMA77_INDEX_BY_NAME[n]] for n in names] for frame in decoded.positions]
        ticks = kimodo_frame_ticks(source)
        reference = mapping['root']['reference_length_meters']
    else:
        raise ValueError('ankle_source_kind_unsupported')
    projected = [[project(_basis(p, mapping['basis']), yaw) for p in frame] for frame in points]
    return dict(profile='source-ankle-displacement-v1', source_bundle_sha256=bundle.bundle_sha256,
                motion_sha256=bundle.clip_sha256, yaw_degrees=yaw, times=[t/1e6 for t in ticks],
                source_reference_length=reference, points=projected,
                authority='none', scope='projected_ankle_displacement_not_floor_contact')


def targets(observation, initial, reference_length):
    """Retain each target's initial ankle placement and all source displacement."""
    if (len(initial) != 2 or any(len(p) != 2 for p in initial)
            or any(not math.isfinite(v) for p in initial for v in p)
            or not math.isfinite(reference_length) or reference_length <= 0):
        raise ValueError('ankle_target_reference_invalid')
    source_length = observation['source_reference_length']
    times, points = observation['times'], observation['points']
    if (not math.isfinite(source_length) or source_length <= 0 or len(times) < 2
            or len(times) != len(points) or times[0] != 0
            or any(not math.isfinite(t) for t in times)
            or any(b <= a for a, b in zip(times, times[1:]))
            or any(len(frame) != 2 or any(len(p) != 3 or any(not math.isfinite(v) for v in p)
                                        for p in frame) for frame in points)):
        raise ValueError('ankle_source_observations_invalid')
    scale = reference_length/source_length
    return [dict(time=t, targets=[[initial[s][0]+(frame[s][0]-points[0][s][0])*scale,
                                  initial[s][1]-(frame[s][1]-points[0][s][1])*scale]
                                 for s in (0, 1)]) for t, frame in zip(times, points)]
