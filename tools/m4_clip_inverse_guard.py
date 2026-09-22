"""Fail closed for the captured Runtime's inverse clipping convexification."""
import math


def convex(points):
    if len(points)<3 or any(len(p)!=2 or not all(math.isfinite(v) for v in p) for p in points):
        raise ValueError('inverse_clip_points')
    area=sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(points,points[1:]+points[:1]))
    if abs(area)<=1e-10:return False
    orientation=1 if area>0 else -1
    # Every point must lie in the same oriented half-plane of every edge.
    # Consecutive turn signs alone would incorrectly accept a star polygon.
    return all(orientation*((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]))>=-1e-10
               for a,b in zip(points,points[1:]+points[:1]) for p in points)


def validate(segments):
    for segment in segments:
        for frame in segment['frames']:
            if not convex(frame['points']):raise ValueError('inverse_clip_concave_runtime_convexifies')
    # Convex keys alone do not prove convex interpolation. This guard blocks known
    # unsupported input; passing it does not grant continuous-time acceptance.
