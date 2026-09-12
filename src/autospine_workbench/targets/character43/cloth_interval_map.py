"""Exact affine dependence of Spine subframe positions on the next cloth key pose."""
from .affine_pose import matrices, sample


def build(document, animation, slot, left, right, previous):
    import numpy as np
    if not 0 <= left < right: raise ValueError('cloth_interval_time')
    data = document['skins'][0]['attachments'][slot][slot]['vertices']
    weights = []; cursor = 0
    while cursor < len(data):
        count = data[cursor]; cursor += 1; row = []
        for _ in range(count):
            bone, _, _, weight = data[cursor:cursor+4]; cursor += 4
            row.append((document['bones'][bone]['name'], weight))
        weights.append(row)
    def linear(t):
        return {name: np.array([[a, b], [c, d]]) for name, (a, b, c, d, _, _) in
                matrices(document, animation, t).items()}
    inverse_left = {k: np.linalg.inv(v) for k, v in linear(left).items()}
    inverse_right = {k: np.linalg.inv(v) for k, v in linear(right).items()}
    before = np.asarray(sample(document, animation, left)[0][slot])
    after = np.asarray(sample(document, animation, right)[0][slot])
    delta = np.asarray(previous)-before; result = []
    for fraction in (.25, .5, .75):
        time = left+(right-left)*fraction; transforms = linear(time)
        a = []; b = []
        for row in weights:
            a.append(sum(w*(transforms[n] @ inverse_left[n]) for n, w in row))
            b.append(sum(w*(transforms[n] @ inverse_right[n]) for n, w in row))
        a = np.asarray(a); b = fraction*np.asarray(b)
        base = np.asarray(sample(document, animation, time)[0][slot])
        bias = base+(1-fraction)*np.einsum('nij,nj->ni', a, delta)-np.einsum('nij,nj->ni', b, after)
        result.append((bias, b))
    return result
