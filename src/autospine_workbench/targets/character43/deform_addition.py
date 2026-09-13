"""Add sampled local displacements while retaining original linear deform keys."""
from bisect import bisect_right
import math


def entries(attachment):
    data = attachment['vertices']; result = []; cursor = 0
    while cursor < len(data):
        count = data[cursor]; cursor += 1; row = []
        if type(count) is not int or count < 1: raise ValueError('deform_addition_weighted_required')
        for _ in range(count):
            index, _, _, weight = data[cursor:cursor+4]; cursor += 4
            row.append((index, weight))
        if abs(sum(w for _, w in row)-1) > 1e-6: raise ValueError('deform_addition_weights')
        result.append(row)
    return result


def local_delta(document, influences, transforms, original, corrected):
    offsets = []
    for row, a, b in zip(influences, original, corrected, strict=True):
        dx, dy = b[0]-a[0], b[1]-a[1]
        for index, _ in row:
            aa, ab, ac, ad, _, _ = transforms[document['bones'][index]['name']]
            determinant = aa*ad-ab*ac
            if abs(determinant) < 1e-10: raise ValueError('deform_addition_singular')
            offsets.extend([(ad*dx-ab*dy)/determinant, (aa*dy-ac*dx)/determinant])
    if not all(math.isfinite(v) for v in offsets): raise ValueError('deform_addition_nonfinite')
    return offsets


def value(keys, time, size):
    if not keys: return [0.]*size
    times = [key['time'] for key in keys]
    i = max(0, bisect_right(times, time)-1); a = keys[i]; b = keys[min(i+1, len(keys)-1)]
    fraction = 0 if time <= a['time'] or a['time'] == b['time'] else (time-a['time'])/(b['time']-a['time'])
    def expanded(key):
        if 'curve' in key: raise ValueError('deform_addition_non_linear_keys')
        output = [0.]*size; start = key.get('offset', 0); vertices = key.get('vertices', [])
        if type(start) is not int or start < 0 or start+len(vertices) > size:
            raise ValueError('deform_addition_offset_invalid')
        output[start:start+len(vertices)] = vertices
        return output
    return [x+fraction*(y-x) for x, y in zip(expanded(a), expanded(b), strict=True)]


def add(original, correction, size):
    times = sorted({k['time'] for k in original+correction})
    if any(b['time'] <= a['time'] for keys in (original, correction) for a, b in zip(keys, keys[1:])):
        raise ValueError('deform_addition_key_order')
    return [dict(time=t, vertices=[a+b for a, b in zip(value(original, t, size),
                 value(correction, t, size), strict=True)]) for t in times]
