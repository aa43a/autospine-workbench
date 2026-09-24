"""Capacity of a constant-width circular fillet, not a general mesh solver.

The hip and ankle stay fixed. Material length is distributed uniformly along
two straight segments and their tangent arc. The inner edge area factor is
lambda * (1 - width / radius); this model may fail when other shapes succeed.
"""
import math


def inspect(hip, knee, ankle, half_width, rest_length, minimum_area=.5):
    values = [*hip, *knee, *ankle, half_width, rest_length, minimum_area]
    if (any(len(p) != 2 for p in (hip, knee, ankle)) or
            not all(math.isfinite(v) for v in values) or
            half_width <= 0 or rest_length <= 0 or not 0 < minimum_area < 1):
        raise ValueError('circular_bend_input')
    u = [knee[i] - hip[i] for i in range(2)]
    v = [ankle[i] - knee[i] for i in range(2)]
    a, b = math.hypot(*u), math.hypot(*v)
    if min(a, b) <= 1e-9:
        raise ValueError('circular_bend_collapsed_segment')
    angle = math.atan2(abs(u[0]*v[1]-u[1]*v[0]), sum(x*y for x, y in zip(u, v)))
    base = dict(turn_degrees=math.degrees(angle), half_width=half_width,
                rest_length=rest_length, chain_length=a+b,
                scope='constant_width_uniform_arclength_tangent_fillet_only')
    if angle < 1e-8:
        ratio = (a+b)/rest_length
        return dict(base, status='straight', maximum_inner_area_factor=ratio,
                    meets_inner_area=ratio >= minimum_area, radius=None)
    if math.pi-angle < 1e-8:
        return dict(base, status='reversal', meets_inner_area=False,
                    radius_limit=0., radius=None)
    tangent = math.tan(angle/2)
    limit = min(a, b)/tangent
    if limit <= half_width:
        return dict(base, status='insufficient_radius', meets_inner_area=False,
                    radius_limit=limit, radius=None)
    loss = 2*tangent-angle
    # Global maximum on width < R <= radius_limit (derivative changes once).
    radius = min(limit, math.sqrt(half_width*(a+b)/loss))
    curve_length = a+b-loss*radius
    factor = curve_length/rest_length*(1-half_width/radius)
    return dict(base, status='evaluated', radius=radius, radius_limit=limit,
                tangent_trim=radius*tangent, curve_length=curve_length,
                maximum_inner_area_factor=factor,
                meets_inner_area=factor >= minimum_area)


def nonuniform_area_bound(hip, knee, ankle, half_width, rest_length, lower=.5, upper=2.):
    """Necessary bound even with nonuniform longitudinal material allocation.

    At curvature 1/R, lower <= lambda*(1-w/R) and
    lambda*(1+w/R) <= upper force R >= w*(upper+lower)/(upper-lower).
    Integrating 1/lambda gives the maximum rest length any such strip can hold.
    This omits edge stretch, seams and global overlap: success is not acceptance.
    """
    row = inspect(hip, knee, ankle, half_width, rest_length, lower)
    if not math.isfinite(upper) or upper <= lower:
        raise ValueError('circular_bend_area_interval')
    theta = math.radians(row['turn_degrees'])
    if row['status'] == 'straight':
        maximum = row['chain_length']/lower
        return dict(status='straight', maximum_rest_length=maximum,
                    necessary_bound_passed=rest_length <= maximum)
    radius = half_width*(upper+lower)/(upper-lower)
    if radius > row.get('radius_limit', 0):
        return dict(status='radius_exceeds_segment', minimum_radius=radius,
                    necessary_bound_passed=False)
    length = row['chain_length']-(2*math.tan(theta/2)-theta)*radius
    maximum = (length-half_width*theta)/lower
    return dict(status='evaluated', minimum_radius=radius,
                maximum_rest_length=maximum, required_rest_length=rest_length,
                necessary_bound_passed=rest_length <= maximum)
