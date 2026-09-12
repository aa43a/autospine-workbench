"""Connected visible-pixel parts and geometric parent proposals, without adoption."""
import math


def _components(points):
    # Kept independent of image/pose dependencies and historical wing profiles.
    remaining=set(points);groups=[]
    while remaining:
        seed=remaining.pop();group={seed};stack=[seed]
        while stack:
            x,y=stack.pop()
            for point in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if point in remaining:remaining.remove(point);group.add(point);stack.append(point)
        groups.append(group)
        if len(groups)>4096:raise ValueError('component_mount_component_limit')
    return sorted(groups,key=lambda group:(-len(group),min((y,x) for x,y in group)))


def partition(alpha,width,height,anchors):
    if type(width) is not int or type(height) is not int or not isinstance(alpha,(bytes,bytearray)) or width<1 or height<1 or width*height>4_000_000 or len(alpha)!=width*height:
        raise ValueError('component_mount_dimensions')
    if not anchors or any(len(p)!=2 or any(not math.isfinite(v) for v in p) for p in anchors.values()):
        raise ValueError('component_mount_anchors')
    points={(i%width,i//width) for i,a in enumerate(alpha) if a>0}
    groups=_components(points);regions=[];residual=[]
    for group in groups:
        indices=sorted(y*width+x for x,y in group)
        if sum(alpha[i]>=8 for i in indices)<64:
            residual.extend(indices);continue
        x0=min(x for x,y in group);y0=min(y for x,y in group)
        x1=max(x for x,y in group)+1;y1=max(y for x,y in group)+1
        candidates=sorted((min(math.dist((x+.5,y+.5),p) for x,y in group),bone) for bone,p in anchors.items())
        regions.append(dict(component_id=f'component-{len(regions):04d}',pixels=indices,bbox=[x0,y0,x1,y1],
            proposed_parent=candidates[0][1],parent_candidates=[dict(bone=b,distance_px=d) for d,b in candidates],
            reason_code='component_parent_review_required'))
    if len(regions)>64: raise ValueError('component_mount_part_limit')
    return dict(profile='connected-alpha-parent-distance-v1',regions=regions,residual_pixels=sorted(residual),
        visible_pixel_count=len(points),authority='none',selected=False)
