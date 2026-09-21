"""Refine failing interpolation times, always solving from the original motion."""
from .affine_area_repair import repair
from .projected_area_sampling import inspect


def build(document,name,setup_vertices,*,samples=129,rounds=3):
    if type(rounds) is not int or not 1 <= rounds <= 5:
        raise ValueError('projected_area_refinement_rounds')
    extra=set();history=[]
    for iteration in range(rounds):
        result,evidence=repair(document,name,samples=samples,convergent=True,
            setup_vertices=setup_vertices,projected_reference=True,extra_times=sorted(extra))
        checked=inspect(result,name,[r['slot'] for r in evidence['records']])
        history.append(dict(iteration=iteration,extra_times=sorted(extra),check=checked))
        new={r['time'] for r in checked['failures'] if not r['at_key']}-extra
        if not new or len(extra|new)>1025:
            break
        extra.update(new)
    evidence.update(profile='adaptive-projected-area-budget10-v1',refinement=history,
                    validation='sampled_proxy_only_original_geometry_gate_retained')
    return result,evidence
