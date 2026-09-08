"""Map framebuffer pixel centers to UV evidence, without assigning ownership."""
import math


def locate(row, camera, size):
    width, height = camera['width'], camera['height']
    cx, cy = camera['world_center']; vw, vh = camera['world_size']
    vertices = list(zip(row['world_vertices'][::2], row['world_vertices'][1::2]))
    uvs = list(zip(row['uvs'][::2], row['uvs'][1::2]))
    if (len(row['world_vertices']) % 2 or len(row['uvs']) % 2 or len(vertices) != len(uvs)
            or len(row['triangles']) % 3 or len(row['targets']) > 4096
            or any(type(i) is not int or not 0 <= i < len(vertices) for i in row['triangles'])):
        raise ValueError('residual_location_geometry')
    if not all(math.isfinite(v) for v in [width, height, cx, cy, vw, vh, *row['world_vertices'], *row['uvs']]):
        raise ValueError('residual_location_nonfinite')
    if min(width, height, vw, vh, *size) <= 0:
        raise ValueError('residual_location_dimensions')
    output = []
    for target in row['targets']:
        px, py = target['pixel']
        if not 0 <= px < width or not 0 <= py < height:
            raise ValueError('residual_location_pixel')
        x, y = cx+((px+.5)/width-.5)*vw, cy+((py+.5)/height-.5)*vh
        match = None
        for i in range(0, len(row['triangles']), 3):
            ids = row['triangles'][i:i+3]
            a, b, c = [vertices[j] for j in ids]
            den = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
            if abs(den) < 1e-12:
                continue
            wa = ((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/den
            wb = ((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/den
            weights = [wa, wb, 1-wa-wb]
            if min(weights) < -1e-6:
                continue
            u, v = [sum(weights[k]*uvs[j][axis] for k, j in enumerate(ids)) for axis in (0, 1)]
            if not all(math.isfinite(n) for n in (u, v)) or not -1e-6 <= u <= 1+1e-6 or not -1e-6 <= v <= 1+1e-6:
                raise ValueError('residual_location_uv')
            sx, sy = u*size[0]-.5, v*size[1]-.5
            texels = sorted({(max(0, min(size[0]-1, tx)), max(0, min(size[1]-1, ty)))
                             for tx in [math.floor(sx), math.floor(sx)+1] for ty in [math.floor(sy), math.floor(sy)+1]})
            match = dict(triangle=ids, texture_sample_xy=[sx, sy], texel_neighborhood=[list(p) for p in texels])
            break
        output.append(dict(target, world_xy=[x, y], mapping=match,
                           status='mapped_sample_not_pixel_ownership' if match else 'outside_raster_triangle'))
    return output


def clusters(points, radius=4):
    """Display grouping only: Chebyshev adjacency, stable ordering, no sample loss."""
    todo = set(range(len(points))); result = []
    while todo:
        first = min(todo); todo.remove(first); group = [first]; pending = [first]
        while pending:
            i = pending.pop(); x, y = points[i]['pixel']
            nearby = sorted(j for j in todo if max(abs(x-points[j]['pixel'][0]), abs(y-points[j]['pixel'][1])) <= radius)
            todo.difference_update(nearby); group.extend(nearby); pending.extend(nearby)
        result.append(sorted(group))
    return result
