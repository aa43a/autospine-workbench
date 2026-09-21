"""Area proxy from bone determinants, independent of deformed mesh winding."""
import math


PROFILE = 'bone-determinant-area-proxy-v1'


def reference(areas, triangles, influences, bones, setup, current):
    factors = {}
    for bone in bones:
        name = bone['name']; a,b,c,d = setup[name][:4]; x,y,z,w = current[name][:4]
        before, after = a*d-b*c, x*w-y*z
        if not math.isfinite(before+after) or before <= 1e-12 or after <= 1e-12:
            raise ValueError('projected_area_orientation_invalid')
        factors[name] = after/before
    vertex_factors = []
    for entries in influences:
        if (not entries or any(not math.isfinite(weight) or weight < 0 for _,weight in entries)
                or abs(sum(weight for _,weight in entries)-1) > 1e-6):
            raise ValueError('projected_area_weights_invalid')
        vertex_factors.append(sum(weight*factors[bones[index]['name']] for index,weight in entries))
    if len(areas) != len(triangles):
        raise ValueError('projected_area_triangle_count')
    # Exact for a same-bone triangle. Mixed-bone arithmetic mean is only a
    # shape prior: never use the determinant of blended transforms, which can
    # itself collapse or invert and would normalize away the error being tested.
    return [a*sum(vertex_factors[i] for i in tri)/3 for a,tri in zip(areas,triangles)]
