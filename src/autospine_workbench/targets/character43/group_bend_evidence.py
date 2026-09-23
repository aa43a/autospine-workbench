"""Source bend evidence for an explicitly chosen view, never visual approval."""
import math

from .oblique_motion import project


def evidence(upper, lower, yaw, *, minimum_height=.01):
    """Sign matches circle_joint's signed perpendicular about start -> end.

    Normalization uses source chain length, so units and projected collapse
    cannot manufacture confidence. No previous-frame sign fills unknown data.
    """
    if (len(upper) != 3 or len(lower) != 3 or
            any(not math.isfinite(v) for v in (*upper, *lower, yaw, minimum_height)) or
            not -90 <= yaw <= 90 or not 0 < minimum_height < 1):
        raise ValueError('bend_evidence_invalid')
    scale = math.hypot(*upper) + math.hypot(*lower)
    if min(math.hypot(*upper), math.hypot(*lower)) <= 1e-12:
        raise ValueError('bend_evidence_zero_bone')
    knee = project(upper, yaw)[:2]
    distal = project(lower, yaw)[:2]
    end = [knee[i] + distal[i] for i in (0, 1)]
    distance = math.hypot(*end)
    if distance / scale <= 1e-8:
        return dict(branch=None, reason='endpoint_projection_collapsed', normalized_height=None)
    height = (end[0]*knee[1] - end[1]*knee[0]) / distance / scale
    return dict(branch=(1 if height > 0 else -1) if abs(height) >= minimum_height else None,
                reason='source_bend_observable' if abs(height) >= minimum_height else 'bend_projection_ambiguous',
                normalized_height=height)


def summarize(segments, times, yaw):
    if not times or any(not math.isfinite(t) for t in times) or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError('bend_times_invalid')
    records = []
    for side in ('left', 'right'):
        upper, lower = [segments[f'humanoid.leg.{part}.{side}'] for part in ('upper', 'lower')]
        if len(upper) != len(times) or len(lower) != len(times):
            raise ValueError('bend_samples_mismatch')
        rows = []
        for time, (origin, vector), (next_origin, distal) in zip(times, upper, lower):
            if math.dist([a+b for a, b in zip(origin, vector)], next_origin) > 1e-6:
                raise ValueError('bend_source_disconnected')
            rows.append(dict(time=time, **evidence(vector, distal, yaw)))
        records.append(dict(side=side, samples=rows,
            counts={str(sign): sum(r['branch'] == sign for r in rows) for sign in (-1, 1, None)},
            observed_switches=[b['time'] for a, b in zip(rows, rows[1:])
                               if a['branch'] is not None and b['branch'] is not None and a['branch'] != b['branch']]))
    return dict(scope='source_bend_in_declared_view_not_target_appearance', yaw_degrees=yaw,
                authority='none', minimum_normalized_height=.01, records=records)
