"""Experimental smooth weights across planes bisecting a continuous bone chain."""
import math

from .mesh_weights import _inputs, _rotate


def _planes(bones):
    directions, lengths = [], []
    for bone in bones:
        delta = [bone['tail_xy'][i]-bone['head_xy'][i] for i in (0, 1)]
        length = math.hypot(*delta)
        if length < 1e-6:
            raise ValueError('joint_plane_degenerate')
        lengths.append(length)
        directions.append([value/length for value in delta])
    planes = []
    for index in (1, 2):
        if math.dist(bones[index-1]['tail_xy'], bones[index]['head_xy']) > 1e-6:
            raise ValueError('joint_plane_disconnected')
        summed = [directions[index-1][i]+directions[index][i] for i in (0, 1)]
        magnitude = math.hypot(*summed)
        if magnitude < 1e-6:
            raise ValueError('joint_plane_degenerate')
        planes.append((bones[index]['head_xy'], [v/magnitude for v in summed],
                       .5*min(lengths[index-1], lengths[index])))
    return planes


def _transition(vertex, plane):
    pivot, normal, halfwidth = plane
    signed = sum((vertex[i]-pivot[i])*normal[i] for i in (0, 1))
    t = max(0., min(1., (signed/halfwidth+1.)*.5))
    return t*t*(3.-2.*t)


def weights_for_vertices(vertices, bones):
    """Keep zero influences explicit; no geometry or vertex position is adjusted."""
    _inputs(vertices, bones)
    planes = _planes(bones)
    weights = []
    for vertex in vertices:
        elbow, wrist = [_transition(vertex, plane) for plane in planes]
        values = [1.-elbow, elbow*(1.-wrist), elbow*wrist]
        weights.append([{'bone_id': bone['id'], 'weight': weight,
                         'local_xy': _rotate([vertex[i]-bone['head_xy'][i] for i in (0, 1)],
                                             -bone['world_rotation_degrees'])}
                        for bone, weight in zip(bones, values)])
    return weights
