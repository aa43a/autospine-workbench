"""World-axis loss for affine two-bone support, relative to the input pose."""
import math


def loss(chains, values):
    total = 0.
    for i, chain in enumerate(chains):
        parent, _, upper, sx, sy, lower, *_ = chain
        du, dl = (math.degrees(v) for v in values[2+i*2:4+i*2])

        def axis(a, b=None):
            a = math.radians(a)
            if b is None:
                x, y = math.cos(a)*sx, math.sin(a)*sx
            else:
                b = math.radians(b)
                x = math.cos(a)*sx*math.cos(b)-math.sin(a)*sy*math.sin(b)
                y = math.sin(a)*sx*math.cos(b)+math.cos(a)*sy*math.sin(b)
            return math.atan2(parent[2]*x+parent[3]*y, parent[0]*x+parent[1]*y)

        for before, after in ((axis(upper), axis(upper+du)),
                              (axis(upper, lower), axis(upper+du, lower+dl))):
            delta = (after-before+math.pi) % (2*math.pi)-math.pi
            total += delta*delta
    return total
