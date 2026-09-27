"""Source limb visibility across explicit views; never an adoption policy."""
import math
from .oblique_motion import project


def scan(vectors, yaws):
    limbs = {k: v for k, v in vectors.items()
             if k.startswith(('humanoid.arm.', 'humanoid.leg.'))}
    if not limbs or any(not points for points in limbs.values()):
        raise ValueError('view_scan_limbs_missing')
    if len({len(points) for points in limbs.values()}) != 1:
        raise ValueError('view_scan_samples_mismatch')
    result = []
    for yaw in yaws:
        if not math.isfinite(yaw) or not -90 <= yaw <= 90:
            raise ValueError('view_scan_yaw_invalid')
        rows = []
        for role, points in sorted(limbs.items()):
            ratios, angles = [], []
            for point in points:
                if len(point) != 3 or any(not math.isfinite(v) for v in point):
                    raise ValueError('view_scan_vector_invalid')
                length = math.sqrt(sum(v*v for v in point))
                if length <= 1e-12:
                    raise ValueError('view_scan_zero_length')
                x, y, _ = project(point, yaw)
                visible = math.hypot(x, y)
                ratios.append(visible / length)
                angles.append(math.degrees(math.atan2(y, x)) if visible > length*1e-6 else None)
            jumps = [abs((b-a+180) % 360-180) for a, b in zip(angles, angles[1:])
                     if a is not None and b is not None]
            index = min(range(len(ratios)), key=ratios.__getitem__)
            rows.append(dict(role=role, minimum_visibility=ratios[index], minimum_frame=index,
                             collapsed_samples=sum(v < .2 for v in ratios),
                             undefined_direction_samples=sum(a is None for a in angles),
                             max_adjacent_angle_degrees=max(jumps, default=None)))
        result.append(dict(yaw_degrees=yaw, records=rows))
    return result
