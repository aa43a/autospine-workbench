"""Vectorized affine endpoint and axis model for a two-leg support window."""
import math
from .affine_pose import matrices
from .affine_leg_ik import _local


def prepare(document, name, times):
    import numpy as np
    bones = {b['name']: b for b in document['bones']}
    tracks = document['animations'][name]['bones']
    rows = []
    for t in times:
        pose = matrices(document, name, t); frame = []
        for side in ('l', 'r'):
            upper, lower, tip = ('thigh_'+side, 'calf_'+side, 'foot_'+side)
            if bones[lower]['parent'] != upper or bones[tip]['parent'] != lower:
                raise ValueError('support_window_chain_invalid')
            ua, _, _, sx, sy = _local(bones[upper], tracks.get(upper, {}), t)
            la, lx, ly, lsx, lsy = _local(bones[lower], tracks.get(lower, {}), t)
            _, tx, ty, _, _ = _local(bones[tip], tracks.get(tip, {}), t)
            if min(sx, sy, lsx, lsy) <= 0:
                raise ValueError('support_window_positive_scale_required')
            frame.append([*pose[bones[upper]['parent']][:4], *pose[upper][4:6],
                          math.radians(ua), sx, sy, math.radians(la), lx, ly, tx*lsx, ty*lsy])
        rows.append(frame)
    return np.asarray(rows)


def evaluate(model, values, reference):
    import numpy as np
    p = model
    upper = p[:, :, 6]+values[:, 2::2]
    lower = p[:, :, 9]+values[:, 3::2]
    cu, su, cl, sl = np.cos(upper), np.sin(upper), np.cos(lower), np.sin(lower)
    sx, sy = p[:, :, 7], p[:, :, 8]
    rx = cl*p[:, :, 12]-sl*p[:, :, 13]
    ry = sl*p[:, :, 12]+cl*p[:, :, 13]
    x, y = sx*(p[:, :, 10]+rx), sy*(p[:, :, 11]+ry)
    vx, vy = cu*x-su*y, su*x+cu*y
    endpoints = np.stack((p[:, :, 4]+p[:, :, 0]*vx+p[:, :, 1]*vy,
                          p[:, :, 5]+p[:, :, 2]*vx+p[:, :, 3]*vy), axis=2)
    endpoints += reference*values[:, None, :2]
    axes = []
    for x, y in ((cu*sx, su*sx), (cu*sx*cl-su*sy*sl, su*sx*cl+cu*sy*sl)):
        axes.append(np.arctan2(p[:, :, 2]*x+p[:, :, 3]*y, p[:, :, 0]*x+p[:, :, 1]*y))
    return endpoints, np.stack(axes, axis=2)
