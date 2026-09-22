"""Fixed four-corner ordinary clips for a linear depth field on one triangle."""
import numpy as np


def rectangles(points, values, *, support=None, boundary_guard=0):
    if not np.isfinite(boundary_guard) or not 0 <= boundary_guard <= .001:
        raise ValueError('halfplane_boundary_guard')
    points = np.asarray(points, dtype=float)
    values = np.asarray(values, dtype=float)
    if points.shape != (3, 2) or values.shape != (3,):
        raise ValueError('halfplane_triangle_shape')
    if not np.isfinite(points).all() or not np.isfinite(values).all():
        raise ValueError('halfplane_nonfinite')
    center = points.mean(axis=0)
    local = points - center
    matrix = np.column_stack((local, np.ones(3)))
    if abs(np.linalg.det(matrix)) <= 1e-10:
        raise ValueError('halfplane_degenerate_triangle')
    gradient = np.linalg.solve(matrix, values)
    length = np.linalg.norm(gradient[:2])
    support = points if support is None else np.asarray(support, dtype=float)
    if support.ndim != 2 or support.shape[1] != 2 or not len(support) or not np.isfinite(support).all():
        raise ValueError('halfplane_support')
    radius = float(np.linalg.norm(support-center, axis=1).max()) + 2
    if length <= 1e-12:
        normal = np.array([1., 0.])
        boundary = -radius if gradient[2] >= 0 else radius
    else:
        normal = gradient[:2] / length
        boundary = float(np.clip(-gradient[2] / length, -radius, radius))
    tangent = np.array([-normal[1], normal[0]])
    extent = radius + 2

    def quad(lower, upper):
        return [(center + normal * x + tangent * y).tolist()
                for x, y in ((lower, -extent), (upper, -extent),
                             (upper, extent), (lower, extent))]

    return dict(front=quad(boundary-boundary_guard, extent), back=quad(-extent, boundary+boundary_guard))


def contains(quad, points, tolerance=1e-8):
    polygon = np.asarray(quad); points = np.asarray(points)
    edges = np.roll(polygon, -1, axis=0) - polygon
    delta = points[:, None, :] - polygon[None, :, :]
    cross = edges[None, :, 0] * delta[:, :, 1] - edges[None, :, 1] * delta[:, :, 0]
    return (cross >= -tolerance).all(axis=1)
