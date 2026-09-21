"""Conservative triangle-box tiles: omitted cells cannot contain mesh overlap."""
import math


def regions(rect, attachments, positions, size=64, *, tight=False):
    x,y,w,h=rect
    if ((w+size-1)//size)*((h+size-1)//size)>4096:
        raise ValueError('depth_overlap_tile_limit')
    occupancy=[]
    for attachment,vertices in zip(attachments,positions):
        indices=attachment['triangles']
        if len(indices)%3 or any(type(i) is not int or not 0<=i<len(vertices) for i in indices):
            raise ValueError('depth_overlap_triangle_indices_invalid')
        cells={}
        for start in range(0,len(indices),3):
            points=[vertices[i] for i in indices[start:start+3]]
            left=max(x,math.floor(min(p[0] for p in points)))
            right=min(x+w,math.ceil(max(p[0] for p in points)))
            top=max(y,math.floor(min(-p[1] for p in points)))
            bottom=min(y+h,math.ceil(max(-p[1] for p in points)))
            if right<=left or bottom<=top:continue
            for row in range((top-y)//size,(bottom-1-y)//size+1):
                for col in range((left-x)//size,(right-1-x)//size+1):
                    box=(max(left,x+col*size),max(top,y+row*size),
                         min(right,x+(col+1)*size),min(bottom,y+(row+1)*size))
                    old=cells.get((col,row),box)
                    cells[col,row]=(min(old[0],box[0]),min(old[1],box[1]),
                                    max(old[2],box[2]),max(old[3],box[3]))
        occupancy.append(cells)
    common=occupancy[0].keys()&occupancy[1].keys()
    if tight:
        result=[]
        for cell in sorted(common,key=lambda p:(p[1],p[0])):
            a,b=occupancy[0][cell],occupancy[1][cell]
            left,top,right,bottom=max(a[0],b[0]),max(a[1],b[1]),min(a[2],b[2]),min(a[3],b[3])
            if right>left and bottom>top:result.append([left,top,right-left,bottom-top])
        return result
    # Disjoint cells retain the original world pixel centres and bilinear sampling.
    return [[x+col*size,y+row*size,min(size,w-col*size),min(size,h-row*size)]
            for col,row in sorted(common,key=lambda p:(p[1],p[0]))]
