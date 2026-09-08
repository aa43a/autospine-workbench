"""Measure perceptible transverse alpha support before widening distal weights."""
from copy import deepcopy
import math
from .joint_plane_weights import _planes, _transition


def measure(image, offset, bones):
    pivot, normal, old = _planes(bones)[1]
    tangent = [-normal[1], normal[0]]
    radius = 0.; count = 0
    for y in range(image.height):
        for x in range(image.width):
            if image.pixels[(y*image.width+x)*4+3] < 8: continue
            d = [x+.5+offset[0]-pivot[0], y+.5+offset[1]-pivot[1]]
            if abs(sum(d[k]*normal[k] for k in (0,1))) > 2*old: continue
            radius = max(radius, abs(sum(d[k]*tangent[k] for k in (0,1))))
            count += 1
    if count == 0: raise ValueError('distal_width_unobservable')
    return {'alpha_samples':count, 'transverse_radius_px':radius, 'original_halfwidth_px':old}


def reweight(row, bones, evidence, factor):
    if type(factor) is not int or factor not in (1,2,4):
        raise ValueError('distal_width_factor_invalid')
    radius = evidence['transverse_radius_px']
    if not math.isfinite(radius) or radius < 0:
        raise ValueError('distal_width_evidence_invalid')
    pivot, normal, old = _planes(bones)[1]
    # Stop the distal transition before the preceding joint; record any cap.
    cap = .45*math.dist(bones[1]['head_xy'], bones[1]['tail_xy'])
    width = max(old, min(cap, factor*radius))
    result = deepcopy(row)
    for vertex, weights in zip(result['vertices_xy'], result['weights']):
        t = _transition(vertex, (pivot, normal, width))
        downstream = weights[1]['weight']+weights[2]['weight']
        weights[1]['weight'] = downstream*(1-t)
        weights[2]['weight'] = downstream*t
    return result, {'factor':factor, 'halfwidth_px':width, 'cap_px':max(old,cap),
                    'capped':factor*radius > max(old,cap)}
