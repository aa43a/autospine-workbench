"""Non-growing, sample-scoped faint edge candidates with actual mesh coverage."""
from .wing_edge_ownership import decode, encode


def covered(x, y, width, height, attachment):
    p = ((x+.5)/width, (y+.5)/height)
    uv = list(zip(attachment['uvs'][::2], attachment['uvs'][1::2]))
    triangles = attachment['triangles']
    for i in range(0, len(triangles), 3):
        a, b, c = [uv[j] for j in triangles[i:i+3]]
        den = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(den) < 1e-12: continue
        wa = ((b[1]-c[1])*(p[0]-c[0])+(c[0]-b[0])*(p[1]-c[1]))/den
        wb = ((c[1]-a[1])*(p[0]-c[0])+(a[0]-c[0])*(p[1]-c[1]))/den
        if min(wa, wb, 1-wa-wb) >= -1e-8: return True
    return False


def transfer(parts, residual, attachments, samples):
    images = {n: decode(r) for n,r in parts.items()}; rest = decode(residual)
    if set(images) != set(attachments) or any(i.size != rest.size for i in images.values()):
        raise ValueError('limb_edge_inventory')
    width, height = rest.size; original = {n: image.copy() for n,image in images.items()}
    offsets = [(dx,dy) for dy in range(-2,3) for dx in range(-2,3) if 0<dx*dx+dy*dy<=4]
    counts = dict(transferred=0, transparent=0, opaque=0, occupied=0, no_neighbor=0, ambiguous=0, outside_mesh=0)
    changes = []
    for x,y in sorted(set(map(tuple,samples))):
        if type(x) is not int or type(y) is not int or not 0<=x<width or not 0<=y<height:
            raise ValueError('limb_edge_sample')
        rgba = rest.getpixel((x,y))
        if not rgba[3]: counts['transparent']+=1; continue
        if rgba[3]>=8: counts['opaque']+=1; continue
        if any(im.getpixel((x,y))[3] for im in original.values()): counts['occupied']+=1; continue
        neighbors = {n for n,im in original.items() if any(0<=x+dx<width and 0<=y+dy<height and im.getpixel((x+dx,y+dy))[3]>=8 for dx,dy in offsets)}
        if not neighbors: counts['no_neighbor']+=1; continue
        if len(neighbors)!=1: counts['ambiguous']+=1; continue
        owner = next(iter(neighbors))
        if not covered(x,y,width,height,attachments[owner]): counts['outside_mesh']+=1; continue
        images[owner].putpixel((x,y),rgba); rest.putpixel((x,y),(0,0,0,0))
        changes.append(dict(local_xy=[x,y],owner=owner,rgba=list(rgba))); counts['transferred']+=1
    # Every changed pixel is a disjoint exact relocation; all other bytes stay in place.
    for row in changes:
        point=tuple(row['local_xy'])
        if images[row['owner']].getpixel(point)!=tuple(row['rgba']) or rest.getpixel(point)!=(0,0,0,0):
            raise ValueError('limb_edge_reconstruction')
    return {n:encode(im) for n,im in images.items()},encode(rest),dict(
        profile='sample-scoped-unique-limb-edge-2px-v1',alpha_range=[1,7],radius_px=2,
        recursive_growth=False,mesh_expansion=False,counts=counts,changes=changes,
        source_pixel_relocation_exact=True,authority='none',production_authorized=False)
