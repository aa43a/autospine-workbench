"""Screen constant gains across poses; necessary bounds never grant acceptance."""
import math
from .area_budget_feasibility import inspect as budget_check
from .single_vertex_area_feasibility import inspect as shared_check
from ..spine43.continuous_pose import area


def screen(poses, gains):
    if not poses or not gains or len(set(gains)) != len(gains):
        raise ValueError('transverse_gain_inventory')
    if any(not math.isfinite(g) or not 0 <= g <= 1 for g in gains):
        raise ValueError('transverse_gain_range')
    rows = []
    for gain in sorted(gains):
        failures = []
        for pose in poses:
            context = pose['context']; floors = pose['floors']
            low, high = pose['zero'], pose['one']
            if len(low) != len(high) or len(low) != len(context['free']):
                raise ValueError('transverse_gain_vertex_inventory')
            points = [[a[k]+gain*(b[k]-a[k]) for k in (0, 1)]
                      for a, b in zip(low, high)]
            budget = budget_check(context, points, [max(.5, f-1e-7) for f in floors])
            shared = shared_check(context, points, floors)
            fixed = []
            for i, (tri, ref, floor) in enumerate(zip(context['row']['triangles'], context['areas'], floors, strict=True)):
                if any(context['free'][v] for v in tri):continue
                ratio = area(points, tri)/ref
                if ratio < max(.5, floor-1e-7) or ratio > 2:
                    fixed.append(i)
            if budget['failures'] or shared['failures'] or fixed:
                failures.append(dict(time=pose['time'], budget=budget['failures'],
                                     shared=shared['failures'], fixed=fixed))
        rows.append(dict(gain=gain, failures=failures))
    feasible = [r['gain'] for r in rows if not r['failures']]
    return dict(profile='constant-transverse-gain-necessary-screen-v1',
                poses=len(poses), trials=rows, unexcluded_gains=feasible,
                suggested_gain=max(feasible) if feasible else None,
                authority='none', selected=False, production_authorized=False,
                scope='sampled_necessary_bounds_not_feasible_solution_or_animation_acceptance')
