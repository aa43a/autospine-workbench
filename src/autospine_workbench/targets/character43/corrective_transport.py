"""Carry prior influence-local correction through current bone transforms."""


def transport(original, influences, offsets, bones, transforms):
    if len(original) != len(influences) or len(offsets) != 2*sum(len(e) for e in influences):
        raise ValueError('corrective_transport_inventory')
    result=[];cursor=0
    for point,entries in zip(original,influences):
        x,y=point
        for index,weight in entries:
            dx,dy=offsets[cursor:cursor+2];cursor+=2
            a,b,c,d=transforms[bones[index]['name']][:4]
            x+=weight*(a*dx+b*dy);y+=weight*(c*dx+d*dy)
        result.append([x,y])
    return result
