"""Experimental elbow-only alternatives and version-neutral local deform offsets."""
import math
from .mesh_weights import _inputs, _weights, _rotate, _frames, _deform
from .joint_plane_weights import weights_for_vertices

MODES = ('lbs', 'half_angle_auxiliary', 'rotation_corrective')


def validate_source(vertices, weights, bones):
    _inputs(vertices, bones)
    if _weights(weights, vertices, bones) > 1e-9 or weights != weights_for_vertices(vertices, bones):
        raise ValueError('elbow_comparison_requires_joint_plane_weights')


def deform(vertices, weights, bones, angle, mode):
    """Fixed proximal bone; connected distal bones inherit the same elbow rotation."""
    if mode not in MODES or type(angle) not in (int, float) or abs(angle) > 90 or not math.isfinite(angle):
        raise ValueError('elbow_probe_invalid')
    if mode == 'lbs':
        return _deform(weights, _frames(bones, angle))
    pivot = bones[1]['head_xy']
    output = []
    for vertex, row in zip(vertices, weights):
        t = row[1]['weight'] + row[2]['weight']
        offset = [vertex[i]-pivot[i] for i in (0, 1)]
        if mode == 'half_angle_auxiliary':
            # One virtual elbow bone at half the bend angle, sharing the elbow pivot.
            middle, distal = _rotate(offset, angle/2), _rotate(offset, angle)
            moved = [(1-t)**2*offset[i]+2*t*(1-t)*middle[i]+t*t*distal[i] for i in (0, 1)]
        else:
            theta = math.radians(angle)
            rotation = math.degrees(math.atan2(t*math.sin(theta), 1-t+t*math.cos(theta)))
            moved = _rotate(offset, rotation)
        output.append([pivot[i]+moved[i] for i in (0, 1)])
    return output


def corrective_offsets(vertices, weights, bones, angle):
    """Per-influence local deltas; no Spine-specific timeline layout implied."""
    validate_source(vertices,weights,bones)
    target = deform(vertices, weights, bones, angle, 'rotation_corrective')
    frames = _frames(bones, angle)
    baseline = _deform(weights, frames)
    return [[_rotate([wanted[i]-actual[i] for i in (0, 1)], -frames[influence['bone_id']][1])
             for influence in row] for wanted, actual, row in zip(target, baseline, weights)]
