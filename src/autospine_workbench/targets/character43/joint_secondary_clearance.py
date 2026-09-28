"""Planar head/torso capsules, comparing ONLY added material penetration.

These are conservative collision proxies. Existing source overlap and the body
animation remain authoritative; this does not determine draw order or 3D depth.
"""
import math


def capsules(pose):
    def point(name): return pose[name][4:6]
    result = []
    shoulder = math.dist(point('upperarm_l'), point('upperarm_r')) if {'upperarm_l', 'upperarm_r'} <= pose.keys() else None
    if {'head', 'neck'} <= pose.keys():
        a, b = point('head'), point('neck'); length = math.dist(a, b)
        if length > 8:
            radius = max(4., min(length*.38, shoulder*.32 if shoulder else length*.38))
            result.append(dict(kind='head', start=a, end=b, radius_px=radius))
    if shoulder and shoulder > 8 and {'chest', 'pelvis'} <= pose.keys():
        a, b = point('chest'), point('pelvis')
        if math.dist(a, b) > 8:
            result.append(dict(kind='torso', start=a, end=b, radius_px=shoulder*.36))
    return result


def penetration(points, proxies):
    result = []
    for x, y in points:
        maximum = 0.
        for row in proxies:
            ax, ay = row['start']; bx, by = row['end']; dx, dy = bx-ax, by-ay
            t = max(0., min(1., ((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy)))
            distance = math.hypot(x-ax-t*dx, y-ay-t*dy)
            maximum = max(maximum, row['radius_px']-distance)
        result.append(maximum)
    return result


def compare(points, baseline, proxies):
    current = penetration(points, proxies)
    increase = max((new-old for new, old in zip(current, baseline, strict=True)), default=0.)
    index = max(range(len(current)), key=lambda i: current[i]-baseline[i], default=None)
    # One image pixel tolerates discrete material vertices/alpha boundary noise.
    return dict(passed=increase <= 1.+1e-7, new_penetration_px=max(0., increase),
                worst_vertex=index, allowed_increase_px=1.,
                baseline_penetration_px=baseline[index] if index is not None else 0.,
                candidate_penetration_px=current[index] if index is not None else 0.)
