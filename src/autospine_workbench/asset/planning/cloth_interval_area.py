"""Exact quadratic area extrema for linearly interpolated world-space triangles."""


def bounds(start, middle, end):
    import numpy as np
    start, middle, end = (np.asarray(v, dtype=float) for v in (start, middle, end))
    a = 2*(end+start-2*middle)
    b = end-start-a
    stationary = np.divide(-b, 2*a, out=np.zeros_like(a), where=np.abs(a) > 1e-12)
    valid = (np.abs(a) > 1e-12) & (stationary > 0) & (stationary < 1)
    value = np.where(valid, (a*stationary+b)*stationary+start, start)
    return np.minimum(np.minimum(start, end), value), np.maximum(np.maximum(start, end), value)
