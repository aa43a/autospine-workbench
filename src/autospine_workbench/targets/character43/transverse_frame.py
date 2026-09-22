"""Experimental material frame: remove inherited shear without moving its axis."""
import math


def without_inherited_shear(rest, current):
    if any(len(m) != 6 or any(not math.isfinite(x) for x in m) for m in (rest, current)):
        raise ValueError('transverse_frame_invalid')
    ra, rb, rc, rd, _, _ = rest
    a, b, c, d, x, y = current
    old_length, length = math.hypot(ra, rc), math.hypot(a, c)
    if min(old_length, length) <= 1e-10 or min(ra*rd-rb*rc, a*d-b*c) <= 1e-10:
        raise ValueError('transverse_frame_singular')
    # Preserve any setup shear under the animated axial scale. Only the extra
    # axial component of the transverse vector is removed; width/determinant,
    # bone origin and every point on the bone axis remain unchanged.
    inherited = (a*b+c*d)/length - (ra*rb+rc*rd)/old_length*length/old_length
    return (a, b-inherited*a/length, c, d-inherited*c/length, x, y), inherited


def weighted_points(attachment, bones, rest, current, selected):
    transforms = dict(current); removed = {}
    if not selected or not set(selected) <= rest.keys() & current.keys():
        raise ValueError('transverse_frame_selection')
    for name in selected:
        transforms[name], removed[name] = without_inherited_shear(rest[name], current[name])
    data = attachment['vertices']; cursor = 0; points = []
    while cursor < len(data):
        count = data[cursor]; cursor += 1
        if type(count) is not int or count < 1 or cursor+4*count > len(data):
            raise ValueError('transverse_frame_weights')
        px = py = total = 0.
        for _ in range(count):
            index, u, v, weight = data[cursor:cursor+4]; cursor += 4
            if (type(index) is not int or not 0 <= index < len(bones)
                    or any(not math.isfinite(z) for z in (u, v, weight)) or weight < 0):
                raise ValueError('transverse_frame_weights')
            a,b,c,d,x,y = transforms[bones[index]['name']]
            px += weight*(a*u+b*v+x); py += weight*(c*u+d*v+y); total += weight
        if abs(total-1) > 1e-6: raise ValueError('transverse_frame_weights')
        points.append([px, py])
    return points, removed
