"""Conservative triangle-box tiles: omitted cells cannot contain mesh overlap."""
import math


def regions(rect, attachments, positions, size=64):
    x,y,w,h=rect
    if ((w+size-1)//size)*((h+size-1)//size)>4096:
        raise ValueError('depth_overlap_tile_limit')
    occupancy=[]
    for attachment,vertices in zip(attachments,positions):
        indices=attachment['triangles']
        if len(indices)%3 or any(type(i) is not int or not 0<=i<len(vertices) for i in indices):
            raise ValueError('depth_overlap_triangle_indices_invalid')
        cells=set()
        for start in range(0,len(indices),3):
            points=[vertices[i] for i in indices[start:start+3]]
            left=max(x,math.floor(min(p[0] for p in points)))
            right=min(x+w,math.ceil(max(p[0] for p in points)))
            top=max(y,math.floor(min(-p[1] for p in points)))
            bottom=min(y+h,math.ceil(max(-p[1] for p in points)))
            if right<=left or bottom<=top:continue
            cells.update((col,row) for row in range((top-y)//size,(bottom-1-y)//size+1)
                         for col in range((left-x)//size,(right-1-x)//size+1))
        occupancy.append(cells)
    common=occupancy[0]&occupancy[1]
    # Disjoint cells retain the original world pixel centres and bilinear sampling.
    return [[x+col*size,y+row*size,min(size,w-col*size),min(size,h-row*size)]
            for col,row in sorted(common,key=lambda p:(p[1],p[0]))]
