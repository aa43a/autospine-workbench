"""Recover a verified material transform, including baked attachment deformation."""
import numpy as np


def fit(reference, current):
    a = np.asarray(reference, dtype=float); b = np.asarray(current, dtype=float)
    if a.ndim != 2 or a.shape[1:] != (2,) or b.shape != a.shape or len(a) < 3:
        raise ValueError('material_frame_shape_invalid')
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('material_frame_nonfinite')
    origin = a.mean(axis=0); scale = np.max(np.linalg.norm(a-origin, axis=1))
    if scale <= 1e-10:
        raise ValueError('material_frame_degenerate')
    design = np.column_stack(((a-origin)/scale, np.ones(len(a))))
    coefficients, _, rank, _ = np.linalg.lstsq(design, b, rcond=None)
    if rank != 3:
        raise ValueError('material_frame_degenerate')
    linear = coefficients[:2].T/scale
    translation = coefficients[2]-linear@origin
    residual = float(np.max(np.linalg.norm(design@coefficients-b, axis=1)))
    # This is a validity check, not a best-fit substitute for flexible material.
    if residual > 1e-5:
        raise ValueError('material_frame_not_affine')
    if np.linalg.det(linear) <= 1e-10:
        raise ValueError('material_frame_orientation_or_area_invalid')
    return (float(linear[0,0]),float(linear[0,1]),float(linear[1,0]),float(linear[1,1]),
            float(translation[0]),float(translation[1])), residual
