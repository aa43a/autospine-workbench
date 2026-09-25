"""Intersect setup and projected area floors without weakening either QA gate."""
import math


def floors(setup_areas, projected_areas):
    if not setup_areas or len(setup_areas)!=len(projected_areas):
        raise ValueError('dual_area_reference_inventory')
    values=[]
    for setup,projected in zip(setup_areas,projected_areas):
        if (not all(math.isfinite(v) for v in (setup,projected)) or
                abs(setup)<1e-12 or abs(projected)<1e-12 or setup*projected<=0):
            raise ValueError('dual_area_reference_invalid')
        factor=setup/projected
        # Solver headroom is stricter than the unchanged .5 independent gates.
        target=max(.505,.505*factor)
        if target>min(2.,2.*factor):
            raise ValueError('dual_area_bounds_infeasible')
        values.append(target)
    return values
