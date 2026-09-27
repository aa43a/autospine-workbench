"""Necessary relative-motion bound; feasible distance alone never proves repair."""
import math
from .material_reachability import inspect


def check(mesh,points,alpha,query,*,cloth_budget=8.,limb_budget=2.,threshold=8.):
    if any(not math.isfinite(x) or x<0 for x in (cloth_budget,limb_budget)) or cloth_budget+limb_budget<=0:
        raise ValueError('joint_coverage_budgets')
    total=cloth_budget+limb_budget
    evidence=inspect(mesh,points,alpha,query,budget=total,threshold=threshold)
    impossible=evidence['status']=='outside_vertex_budget'
    return dict(status='outside_joint_displacement_budget' if impossible else 'not_ruled_out',
        cloth_budget_px=cloth_budget,limb_budget_px=limb_budget,relative_budget_px=total,
        query=list(query),evidence=evidence,authority='none',selected=False,
        limitation='necessary_bound_for_fixed_uv_material_points_not_global_solver_or_framebuffer_proof')
