"""Split source triangles into two half surfaces with overlapping polygon caps.

No texels are synthesized. UVs are barycentrically interpolated. Each original
half is retained, while the opposite half inside an inscribed disk is copied.
Alpha overdraw and depth order are deliberately left to independent validation.
"""
import math


def split(points, uvs, triangles, center, axis, radius, segments=32):
    if (len(points) != len(uvs) or len(center) != 2 or len(axis) != 2 or
            any(len(p) != 2 for p in [*points, *uvs]) or
            not all(math.isfinite(x) for p in [*points, *uvs, center, axis] for x in p) or
            not math.isfinite(radius) or radius <= 0 or type(segments) is not int or segments < 8):
        raise ValueError('joint_caps_input')
    length = math.hypot(*axis)
    if length <= 1e-10:
        raise ValueError('joint_caps_axis')
    axis = [x/length for x in axis]
    source = [[*p, *uv] for p, uv in zip(points, uvs)]

    def clip(poly, normal, bound):
        result = []
        for a, b in zip(poly, poly[1:]+poly[:1]):
            da = sum((a[i]-center[i])*normal[i] for i in (0, 1))-bound
            db = sum((b[i]-center[i])*normal[i] for i in (0, 1))-bound
            if da <= 0:
                result.append(a)
            if (da <= 0) != (db <= 0):
                f = da/(da-db)
                result.append([x+f*(y-x) for x, y in zip(a, b)])
        return result

    output = []
    for sign in (1, -1):
        part = dict(points=[], uvs=[], triangles=[])
        cache = {}

        def append(poly):
            for i in range(1, len(poly)-1):
                a, b, c = poly[0], poly[i], poly[i+1]
                area = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
                if abs(area) <= 1e-10:
                    continue
                ids = []
                for p in (a, b, c):
                    key = tuple(round(x, 10) for x in p)
                    if key not in cache:
                        cache[key] = len(part['points'])
                        part['points'].append(p[:2])
                        part['uvs'].append(p[2:])
                    ids.append(cache[key])
                part['triangles'].append(ids)

        for tri in triangles:
            if len(tri) != 3 or any(type(i) is not int or not 0 <= i < len(points) for i in tri):
                raise ValueError('joint_caps_triangles')
            polygon = [source[i] for i in tri]
            append(clip(polygon, [sign*x for x in axis], 0))
            cap = clip(polygon, [-sign*x for x in axis], 0)
            for i in range(segments):
                angle = (i+.5)*2*math.pi/segments
                cap = clip(cap, [math.cos(angle), math.sin(angle)], radius*math.cos(math.pi/segments))
                if not cap:
                    break
            append(cap)
        output.append(part)
    return output
