"""Conservative same-time bounding rejection for partitioned mesh relations."""
import math


class SampledRegionBounds:
    def __init__(self, slots):
        self.slots=tuple(slots);self.frames={};self.cache={}

    def record(self,time,positions):
        if time in self.frames:raise ValueError('region_bounds_duplicate_time')
        bounds={}
        for slot in self.slots:
            points=positions[slot]
            if not points or any(not math.isfinite(v) for p in points for v in p):
                raise ValueError('region_bounds_positions')
            xs,ys=zip(*points)
            # One native pixel on each side retains edge/raster uncertainty.
            bounds[slot]=(min(xs)-1,min(ys)-1,max(xs)+1,max(ys)+1)
        self.frames[time]=bounds

    def possible(self,a,b,frames):
        times=tuple(f['time'] for f in frames)
        key=(tuple(sorted((a,b))),times)
        if key not in self.cache:
            possible=False
            for time in times:
                if time not in self.frames:raise ValueError('region_bounds_missing_time')
                x,y=self.frames[time][a],self.frames[time][b]
                possible |= max(x[0],y[0])<=min(x[2],y[2]) and max(x[1],y[1])<=min(x[3],y[3])
            self.cache[key]=possible
        return self.cache[key]
