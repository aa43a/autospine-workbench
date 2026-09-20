"""Disjoint native-pixel tiles and a shared-budget view for depth classification."""


def tiles(rect):
    x,y,w,h=rect
    if ((w+255)//256)*((h+255)//256)>64:
        raise ValueError('depth_overlap_tile_limit')
    return [[a,b,min(256,x+w-a),min(256,y+h-b)]
            for b in range(y,y+h,256) for a in range(x,x+w,256)]


class TileProbe:
    def __init__(self,probe,result): self.probe,self.result=probe,result
    def __getattr__(self,name): return getattr(self.probe,name)
    @property
    def remaining(self): return self.probe.remaining
    @remaining.setter
    def remaining(self,value): self.probe.remaining=value
    def pair(self,a,b,time): return self.result
