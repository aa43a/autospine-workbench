"""Experimental planar dual-quaternion blend with retained polar stretch.

Unlike independent pivot interpolation, rotation and translation are coupled.
This preserves each single influence exactly; it does not guarantee a fold-free
surface, seam continuity, or a temporally consistent branch near half-turns.
"""
import math
import numpy as np


def blend(point, transforms, weights):
    weights = np.asarray(weights, dtype=float)
    point = np.asarray(point, dtype=float)
    if (point.shape != (2,) or len(transforms) != len(weights) or not len(weights)
            or not np.isfinite([*point, *weights]).all() or np.any(weights < 0)
            or abs(weights.sum()-1) > 1e-6):
        raise ValueError('dual_rotation_input')
    rotations, duals, stretch = [], [], np.zeros((2, 2))
    for frame, weight in zip(transforms, weights):
        if len(frame) != 6 or not np.isfinite(frame).all():
            raise ValueError('dual_rotation_frame')
        a, b, c, d, x, y = frame
        linear = np.array([[a, b], [c, d]])
        if np.linalg.det(linear) <= 1e-10:
            raise ValueError('dual_rotation_reflection_or_collapse')
        u, singular, vt = np.linalg.svd(linear)
        rotation = u @ vt
        half = math.atan2(rotation[1, 0], rotation[0, 0])/2
        cosine, sine = math.cos(half), math.sin(half)
        rotations.append(np.array([cosine, sine]))
        duals.append(np.array([x*cosine+y*sine, -x*sine+y*cosine])/2)
        stretch += weight*(vt.T @ np.diag(singular) @ vt)
    reference = rotations[int(np.argmax(weights))]
    q, dual = np.zeros(2), np.zeros(2)
    for rotation, translation, weight in zip(rotations, duals, weights):
        dot = float(reference @ rotation)
        if weight > 0 and abs(dot) < 1e-7:
            raise ValueError('dual_rotation_half_turn_branch_ambiguous')
        sign = -1 if dot < 0 else 1
        q += weight*sign*rotation
        dual += weight*sign*translation
    norm = np.linalg.norm(q)
    if norm <= 1e-10:
        raise ValueError('dual_rotation_cancelled')
    q /= norm; dual /= norm
    c, s = q; dx, dy = dual
    rotation = np.array([[c*c-s*s, -2*c*s], [2*c*s, c*c-s*s]])
    translation = 2*np.array([dx*c-dy*s, dx*s+dy*c])
    return (rotation @ stretch @ point + translation).tolist()


def weighted_points(attachment, bones, rest, current):
    frames, bases = {}, {}
    for bone in bones:
        name = bone['name']
        a, b, c, d, x, y = rest[name]
        base = np.array([[a, b], [c, d]])
        a, b, c, d, tx, ty = current[name]
        linear = np.array([[a, b], [c, d]]) @ np.linalg.inv(base)
        shift = np.array([tx, ty])-linear @ [x, y]
        frames[name] = [*linear.ravel(), *shift]
        bases[name] = (base, np.array([x, y]))
    data, cursor, result = attachment['vertices'], 0, []
    while cursor < len(data):
        count = data[cursor]; cursor += 1
        if type(count) is not int or count < 1 or cursor+4*count > len(data):
            raise ValueError('dual_rotation_weighted_mesh_required')
        points, transforms, weights = [], [], []
        for _ in range(count):
            index, x, y, weight = data[cursor:cursor+4]; cursor += 4
            if type(index) is not int or not 0 <= index < len(bones):
                raise ValueError('dual_rotation_bone_index')
            name = bones[index]['name']; base, origin = bases[name]
            points.append(base @ [x, y]+origin)
            transforms.append(frames[name]); weights.append(weight)
        if max(np.linalg.norm(p-points[0]) for p in points) > 1e-4:
            raise ValueError('dual_rotation_inconsistent_bind')
        result.append(blend(points[0], transforms, weights))
    return result
