"""Depth observations in the same continuous camera basis as live pose fitting."""
import math
from ...resolved_project import canonical_sha256
from .camera_track import PROFILE, at_times, validate


def angles(ticks, keys):
    times = [tick / 1_000_000 for tick in ticks]
    if not times:
        raise ValueError('camera_depth_samples_empty')
    return at_times(keys, times, times[-1])


def project(x, depth, yaw):
    angle = math.radians(yaw)
    return math.sin(angle)*x + math.cos(angle)*depth


def receipt(keys, ticks):
    yaws = angles(ticks, keys)
    track = validate(keys, ticks[-1]/1_000_000)
    return dict(profile=PROFILE, keys=track, track_sha256=canonical_sha256(track),
                samples=[dict(source_tick=t, yaw_degrees=y) for t, y in zip(ticks, yaws)],
                scope='source_depth_in_continuous_camera_basis_not_pixel_visibility')
