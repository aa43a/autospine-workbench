"""Directed boundaries of thresholded, deformed CPU alpha; no adoption authority."""
import math


def edges(mask, rect):
    """Exclude artificial ROI borders; outward normals use world Y-up coordinates."""
    height, width = mask.shape; result = []
    for y, x in zip(*mask.nonzero()):
        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
            xx, yy = x+dx, y+dy
            if not (0 <= xx < width and 0 <= yy < height) or mask[yy,xx]:
                continue
            cx, cy = rect[0]+x+.5+dx*.5, -(rect[1]+y+.5+dy*.5)
            tangent = (0,.5) if dx else (.5,0)
            result.append(dict(a=[float(cx-tangent[0]),float(cy-tangent[1])],
                               b=[float(cx+tangent[0]),float(cy+tangent[1])], normal=[dx,-dy]))
    return result


def nearest(point, boundary):
    options = []
    for edge in boundary:
        a,b = edge['a'],edge['b']; dx,dy = b[0]-a[0],b[1]-a[1]
        t = max(0.,min(1.,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/(dx*dx+dy*dy)))
        q = [a[0]+t*dx,a[1]+t*dy]; distance = math.dist(point,q)
        facing = sum((point[i]-q[i])*edge['normal'][i] for i in (0,1))/distance if distance else 0.
        options.append(dict(point=q,normal=edge['normal'],distance=distance,facing=facing))
    if not options: return []
    minimum = min(o['distance'] for o in options)
    return [o for o in options if o['distance'] <= minimum+1e-9]


def outside_reachable(union):
    """Four-connected empty space reaching the ROI edge, not proven global exterior."""
    height,width = union.shape; seen = set(); stack = []
    for y in range(height):
        for x in range(width):
            if (x in (0,width-1) or y in (0,height-1)) and not union[y,x]:
                seen.add((y,x)); stack.append((y,x))
    while stack:
        y,x = stack.pop()
        for dy,dx in ((0,1),(0,-1),(1,0),(-1,0)):
            q = (y+dy,x+dx)
            if 0<=q[0]<height and 0<=q[1]<width and q not in seen and not union[q]:
                seen.add(q); stack.append(q)
    return seen


def probe(point, boundaries):
    choices = [nearest(point,b) for b in boundaries]
    status = 'insufficient_boundary_evidence'
    if all(choices) and all(c[0]['distance']<=4 for c in choices):
        flags = [a['facing']>=.5 and b['facing']>=.5 and
                 sum(x*y for x,y in zip(a['normal'],b['normal']))<=-.5
                 for a in choices[0] for b in choices[1]]
        status = 'opposed_facing_boundaries' if all(flags) else 'ambiguous_boundary_ties' if any(flags) else 'no_opposed_nearest_boundaries'
    return dict(world_point=point, driver_nearest=choices[0], follower_nearest=choices[1], evidence=status)
