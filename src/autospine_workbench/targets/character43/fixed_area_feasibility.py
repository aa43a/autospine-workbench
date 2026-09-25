"""Necessary area feasibility for triangles whose vertices cannot move."""
import math
from ..spine43.continuous_pose import area


class FixedAreaInfeasible(ValueError):
    def __init__(self,report):
        super().__init__('fixed_vertices_dual_area_infeasible')
        self.report=report


def inspect(slot,triangles,setup_areas,free,times,worlds,projected_areas):
    if len(times)!=len(worlds) or len(times)!=len(projected_areas) or len(triangles)!=len(setup_areas):
        raise ValueError('fixed_area_inventory_invalid')
    fixed=[i for i,t in enumerate(triangles) if all(not free[v] for v in t)]
    failures=[]
    for time,points,refs in zip(times,worlds,projected_areas):
        if len(refs)!=len(triangles):raise ValueError('fixed_area_inventory_invalid')
        for i in fixed:
            actual=area(points,triangles[i]);base=setup_areas[i];ref=refs[i]
            if not all(math.isfinite(v) for v in (actual,base,ref)) or min(abs(base),abs(ref))<1e-12:
                raise ValueError('fixed_area_reference_invalid')
            setup_ratio=actual/base;projected_ratio=actual/ref
            if not (.5<=setup_ratio<=2 and .5<=projected_ratio<=2):
                failures.append(dict(time=time,triangle=i,setup_ratio=setup_ratio,projected_ratio=projected_ratio))
    return dict(status='infeasible_fixed_vertices' if failures else 'no_fixed_triangle_counterexample',
                slot=slot,fixed_triangles=len(fixed),sample_count=len(times),failures=failures,
                authority='none',selected=False,scope='necessary_fixed_vertex_condition_not_complete_feasibility_or_visual_acceptance')
