"""Locate setup occlusion transitions; these are not confirmed garment seams."""
import numpy as np


def locate(arm_alpha, body_alpha, world, covered, root, radius):
    """Cross a body alpha threshold only inside continuous visible arm material.

    Pixel samples are at texel centers. Crossing locations interpolate the two
    samples; this is a diagnostic approximation, not a GPU alpha contour.
    Filtering by radius must never manufacture an arc on the radius boundary.
    """
    arm = np.asarray(arm_alpha)
    body = np.asarray(body_alpha)
    points = np.asarray(world, float)
    valid = np.asarray(covered, bool)
    origin = np.asarray(root, float)
    if (arm.ndim != 2 or body.shape != arm.shape or valid.shape != arm.shape
            or points.shape != (*arm.shape, 2) or origin.shape != (2,)
            or not np.isfinite(origin).all() or not np.isfinite(radius) or radius <= 0
            or not np.isfinite(arm).all() or not np.isfinite(body).all()
            or np.any((arm < 0) | (arm > 255) | (body < 0) | (body > 255))
            or not np.isfinite(points[valid]).all()):
        raise ValueError('material_frontier_input_invalid')
    height, width = arm.shape
    records = []
    for axis in (0, 1):
        left = (slice(None, -1), slice(None)) if axis == 0 else (slice(None), slice(None, -1))
        right = (slice(1, None), slice(None)) if axis == 0 else (slice(None), slice(1, None))
        crossing = ((body[left] >= 254) != (body[right] >= 254))
        support = valid[left] & valid[right] & (arm[left] >= 8) & (arm[right] >= 8)
        ys, xs = np.where(crossing & support)
        for y, x in zip(ys.tolist(), xs.tolist()):
            other_y, other_x = y + (axis == 0), x + (axis == 1)
            a, b = float(body[y, x]), float(body[other_y, other_x])
            fraction = (254 - a) / (b - a)
            p = points[y, x] * (1 - fraction) + points[other_y, other_x] * fraction
            if np.linalg.norm(p - origin) > radius:
                continue
            uv = [(x + .5 + fraction * (axis == 1)) / width,
                  (y + .5 + fraction * (axis == 0)) / height]
            records.append(dict(edge=[[y, x], [other_y, other_x]],
                                fraction=fraction, uv=uv, world=p.tolist()))
    return dict(profile='setup-material-occlusion-frontier-v1', alpha_threshold=254,
                arm_visible_threshold=8, radius_px=float(radius), samples=records,
                authority='none', selected=False,
                scope='occlusion_transition_not_semantic_seam_or_gpu_contour')
