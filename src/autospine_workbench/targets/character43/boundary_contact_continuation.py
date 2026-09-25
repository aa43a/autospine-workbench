"""Find a seed through intermediate targets; only the original final target can pass."""
from copy import deepcopy
from .boundary_shape_feasible import refine
from .boundary_path_feasibility import inspect as path_bounds


def solve(setup, triangles, world, fixed, free, regions, budget, *, steps=8):
    if type(steps) is not int or not 2 <= steps <= 32:
        raise ValueError('contact_continuation_steps_invalid')
    bound = path_bounds(setup, triangles, fixed, free)
    report = dict(profile='fixed-budget-contact-continuation-v1',authority='none',selected=False,
                  scope='single_pose_solver_not_animation_or_visual_acceptance',steps=steps,stages=[])
    if bound['status']=='fixed_boundary_path_conflict':
        return deepcopy(world),dict(report,status='fixed_constraint_conflict',path_bound=bound)
    seed=deepcopy(world)
    for index in range(1,steps+1):
        fraction=index/steps
        target=[[a+(b-a)*fraction for a,b in zip(p,q)] for p,q in zip(world,fixed)]
        contacts=[]
        for region in regions:
            row=deepcopy(region);p=world[row['vertex']]
            row['center']=[a+(b-a)*fraction for a,b in zip(p,region['center'])]
            contacts.append(row)
        # Avoid roundoff changing the last constraint set: validate exactly the
        # caller's target, region shapes and original world-relative budget.
        if index==steps:target=fixed;contacts=regions
        points,evidence=refine(setup,triangles,target,free,world,seed,budget,regions=contacts)
        report['stages'].append(dict(fraction=fraction,**evidence))
        if evidence['status']!='feasible_candidate':
            return deepcopy(world),dict(report,status='no_feasible_candidate_found',stopped_fraction=fraction)
        seed=points
    return seed,dict(report,status='feasible_candidate',final=report['stages'][-1])
