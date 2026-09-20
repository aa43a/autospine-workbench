"""Experimental hand-axis extent from opaque, strongly hand-weighted vertices."""
import math
from collections import defaultdict

PROFILE = 'opaque-dominant-hand-mesh-axis-v1-experiment'


def infer(document, mesh, alpha):
    used=set(mesh['triangles']); data=mesh['vertices']; cursor=0; vertex=0; support=defaultdict(list)
    height,width=alpha.shape
    while cursor<len(data):
        count=data[cursor]; cursor+=1; weights=data[cursor:cursor+4*count]; cursor+=4*count
        if vertex in used:
            u,v=mesh['uvs'][2*vertex:2*vertex+2]; tx=u*width-.5; ty=v*height-.5
            ix,iy=math.floor(tx),math.floor(ty); opacity=0
            for dx,dy in ((0,0),(1,0),(0,1),(1,1)):
                xx,yy=ix+dx,iy+dy
                if 0<=xx<width and 0<=yy<height:
                    opacity+=float(alpha[yy,xx])*(tx-ix if dx else 1-tx+ix)*(ty-iy if dy else 1-ty+iy)
            for i in range(0,len(weights),4):
                index,x,y,weight=weights[i:i+4]; bone=document['bones'][index]
                if bone['name'] in ('hand_l','hand_r') and weight>=.9 and opacity>=8 and x>0:
                    support[bone['name']].append(dict(vertex=vertex,x=x,weight=weight,alpha=opacity))
        vertex+=1
    axes={}
    for bone,rows in sorted(support.items()):
        if len(rows)<3 or len({r['x'] for r in rows})<2: continue
        axes[bone]=dict(length=max(r['x'] for r in rows),support=rows)
    return dict(profile=PROFILE,axes=axes,authority='none',selected=False,
                minimum_weight=.9,alpha_threshold=8,
                assumption='wrist_origin_to_distal_opaque_dominant_hand_support_not_display_bone_length')
