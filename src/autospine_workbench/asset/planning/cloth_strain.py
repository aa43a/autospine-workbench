"""Triangle principal stretches, independent of canvas rotation or scale."""


def prepare(setup, triangles):
    import numpy as np
    points = np.asarray(setup, dtype=float); tri = np.asarray(triangles, dtype=int)
    rest = np.stack((points[tri[:, 1]]-points[tri[:, 0]], points[tri[:, 2]]-points[tri[:, 0]]), axis=2)
    if not np.isfinite(rest).all() or np.any(np.abs(np.linalg.det(rest)) < 1e-10):
        raise ValueError('cloth_strain_degenerate')
    return tri, np.linalg.inv(rest)


def stretches(points, context):
    import numpy as np
    tri, inverse = context; p = np.asarray(points, dtype=float)
    current = np.stack((p[tri[:, 1]]-p[tri[:, 0]], p[tri[:, 2]]-p[tri[:, 0]]), axis=2)
    gradient = current @ inverse
    if not np.isfinite(gradient).all(): raise ValueError('cloth_strain_nonfinite')
    trace = np.sum(gradient*gradient, axis=(1, 2)); determinant = np.linalg.det(gradient)
    high = np.sqrt(np.maximum(0, (trace+np.sqrt(np.maximum(0, trace*trace-4*determinant**2)))/2))
    low = np.divide(np.abs(determinant), high, out=np.zeros_like(high), where=high > 1e-12)
    return low, high
