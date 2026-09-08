"""Bounded local triangle transport; disagreement retains unknown associations."""
import math


def barycentric(point, triangle):
    a, b, c = triangle
    ux, uy = b[0]-a[0], b[1]-a[1]; vx, vy = c[0]-a[0], c[1]-a[1]
    determinant = ux*vy-uy*vx
    if abs(determinant) < 1e-10:
        raise ValueError('gap_transport_degenerate_triangle')
    px, py = point[0]-a[0], point[1]-a[1]
    u, v = (px*vy-py*vx)/determinant, (ux*py-uy*px)/determinant
    return [1-u-v, u, v]


def distance(point, triangle, weights):
    if min(weights) >= 0:
        return 0.
    distances = []
    for a, b in zip(triangle, triangle[1:]+triangle[:1]):
        dx, dy = b[0]-a[0], b[1]-a[1]; length = dx*dx+dy*dy
        t = max(0., min(1., ((point[0]-a[0])*dx+(point[1]-a[1])*dy)/length)) if length else 0.
        distances.append(math.dist(point, [a[0]+t*dx, a[1]+t*dy]))
    return min(distances)


def predict(point, previous, current, triangles):
    """Affine extension of the nearest mesh triangle, at most 4px outside it.

    Tied nearest triangles must predict within 1px. This is geometric support,
    not an alpha observation or proof that a transparent pixel belongs to a mesh.
    """
    candidates = []
    if not all(math.isfinite(v) for p in [point, *previous, *current] for v in p):
        raise ValueError('gap_transport_nonfinite')
    for offset in range(0, len(triangles), 3):
        indices = triangles[offset:offset+3]
        source = [previous[i] for i in indices]; target = [current[i] for i in indices]
        weights = barycentric(point, source)
        d = distance(point, source, weights)
        predicted = [sum(w*p[axis] for w, p in zip(weights, target)) for axis in (0, 1)]
        candidates.append((d, predicted))
    if not candidates:
        return None
    nearest = min(d for d, _ in candidates)
    if nearest > 4:
        return None
    points = [p for d, p in candidates if d <= nearest+1e-8]
    if any(math.dist(a, b) > 1 for a in points for b in points):
        return None
    return [sum(p[i] for p in points)/len(points) for i in (0, 1)]


def compare(a, b, poses, attachments, names):
    errors = []; predictions = []
    for source, target in ((a, b), (b, a)):
        guesses = [predict(source['centroid'], poses[source['frame']][n], poses[target['frame']][n],
                           attachments[n][n]['triangles']) for n in names]
        if any(p is None for p in guesses):
            return dict(status='unsupported_transport', distance=None)
        if math.dist(*guesses) > 1:
            return dict(status='attachment_motion_disagreement', distance=None)
        predicted = [(guesses[0][i]+guesses[1][i])/2 for i in (0, 1)]
        errors.append(math.dist(predicted, target['centroid'])); predictions.append(predicted)
    residual = max(errors)
    return dict(status='within_residual' if residual <= 3 else 'residual_exceeded', distance=residual,
                forward_prediction=predictions[0], backward_prediction=predictions[1])
