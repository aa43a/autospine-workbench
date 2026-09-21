"""Opt-in refinement of inclusive-raster contacts on common source vertices."""


def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def intersection_area(a,b):
    orientation=cross(*b)
    if orientation==0:return None
    polygon=list(a);sign=1 if orientation>0 else -1
    for left,right in zip(b,b[1:]+b[:1]):
        output=[]
        for p,q in zip(polygon,polygon[1:]+polygon[:1]):
            dp=sign*cross(left,right,p);dq=sign*cross(left,right,q)
            if dp>=0:output.append(p)
            if (dp<0<dq) or (dq<0<dp):
                t=dp/(dp-dq);output.append([p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1])])
        polygon=output
        if not polygon:return 0.
    origin=polygon[0]
    return abs(sum(cross(origin,p,q) for p,q in zip(polygon,polygon[1:]+polygon[:1])))/2


class BoundaryProbe:
    def __init__(self,probe,partition,*,pair_limit=200000):
        self.base=probe;self.regions={r['slot']:r for r in partition['regions']}
        self.cache={};self.records=[];self.checked=0;self.limit=pair_limit;self.limit_reached=False

    @property
    def remaining(self):return self.base.remaining

    def pair(self,a,b,time):
        key=(min(a,b),max(a,b),time)
        if key in self.cache:return self.cache[key]
        original=self.base.pair(a,b,time);result=original
        if original['overlap_pixels'] and self._boundary_only(a,b,time):
            result=dict(original,overlap_pixels=0,inclusive_raster_overlap_pixels=original['overlap_pixels'],
                        refinement='common_source_vertices_zero_intersection_area')
            self.records.append(dict(pair=[a,b],time=time,inclusive_raster_overlap_pixels=original['overlap_pixels']))
        self.cache[key]=result;return result

    def _boundary_only(self,a,b,time):
        ra,rb=self.regions.get(a),self.regions.get(b)
        if not ra or not rb or ra['source_slot']!=rb['source_slot']:return False
        doc=self.base.document;points=self.base.positions[time];meshes=doc['skins'][0]['attachments']
        ma=meshes[a][self.base.slots[a]['attachment']];mb=meshes[b][self.base.slots[b]['attachment']]
        found=False
        for i in range(0,len(ma['triangles']),3):
            ia=ma['triangles'][i:i+3];pa=[points[a][v] for v in ia]
            for j in range(0,len(mb['triangles']),3):
                ib=mb['triangles'][j:j+3];pb=[points[b][v] for v in ib]
                if any(max(p[k] for p in pa)<min(p[k] for p in pb) or max(p[k] for p in pb)<min(p[k] for p in pa) for k in (0,1)):continue
                if self.checked>=self.limit:self.limit_reached=True;return False
                self.checked+=1
                shared={ra['source_vertex_indices'][v] for v in ia}&{rb['source_vertex_indices'][v] for v in ib}
                if not shared or cross(*pa)==0:return False
                # No epsilon: tiny positive or numerically uncertain area stays protected.
                if intersection_area(pa,pb)!=0:return False
                for vertex in shared:
                    if points[a][ra['source_vertex_indices'].index(vertex)]!=points[b][rb['source_vertex_indices'].index(vertex)]:return False
                found=True
        return found
