"""Independent linear timeline/FK evaluation for diagnostic weighted meshes."""
import math


def interpolate(keys,time,field):
    i=0
    while i+1<len(keys) and keys[i+1]['time']<=time:i+=1
    a=keys[i];b=keys[min(i+1,len(keys)-1)]
    f=0 if a.get('curve')=='stepped' or a['time']==b['time'] else (time-a['time'])/(b['time']-a['time'])
    if field=='value':return a[field]+f*(b[field]-a[field])
    return [x+f*(y-x) for x,y in zip(a[field],b[field])]


def world(doc,time):
    animation=next(iter(doc['animations'].values()));frames={};result={}
    def rotate(x,y,a):
        a=math.radians(a);return x*math.cos(a)-y*math.sin(a),x*math.sin(a)+y*math.cos(a)
    for bone in doc['bones']:
        x,y,a=frames.get(bone.get('parent'),(0,0,0));dx,dy=rotate(bone['x'],bone['y'],a)
        keys=animation['bones'].get(bone['name'],{}).get('rotate')
        frames[bone['name']]=(x+dx,y+dy,a+bone['rotation']+(interpolate(keys,time,'value') if keys else 0))
    for name,slot in doc['skins'][0]['attachments'].items():
        data=slot[name]['vertices'];keys=animation.get('attachments',{}).get('default',{}).get(name,{}).get(name,{}).get('deform')
        offsets=interpolate(keys,time,'vertices') if keys else [];i=0;j=0;points=[]
        while i<len(data):
            count=data[i];i+=1;x=y=0
            for _ in range(count):
                index,lx,ly,w=data[i:i+4];i+=4
                if offsets:lx+=offsets[j];ly+=offsets[j+1]
                j+=2;bx,by,a=frames[doc['bones'][index]['name']];dx,dy=rotate(lx,ly,a)
                x+=(bx+dx)*w;y+=(by+dy)*w
            points.append([x,y])
        result[name]=points
    return result


def area(points,tri):
    a,b,c=(points[i] for i in tri)
    return ((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2


def inspect(doc):
    """121 fixed samples; seam proxy never asserts alpha/raster seam coverage."""
    setup=world(doc,0);attachments=doc['skins'][0]['attachments'];rows={}
    samples=[world(doc,i/60) for i in range(121)]
    for name,points in setup.items():
        flat=attachments[name][name]['triangles'];triangles=[flat[i:i+3] for i in range(0,len(flat),3)]
        areas=[area(points,t) for t in triangles]
        if any(abs(a)<1e-12 for a in areas):raise ValueError('continuous_degenerate_setup')
        edges=sorted({tuple(sorted((t[i],t[(i+1)%3]))) for t in triangles for i in range(3)})
        ratios=[area(s[name],t)/a for s in samples for t,a in zip(triangles,areas)]
        stretch=max(math.dist(s[name][a],s[name][b])/math.dist(points[a],points[b]) for s in samples for a,b in edges)
        loop=max(math.dist(a,b) for a,b in zip(samples[0][name],samples[-1][name]))
        finite=all(math.isfinite(v) for s in samples for p in s[name] for v in p)
        rows[name]={'passed':finite and min(ratios)>=.5 and max(ratios)<=2 and stretch<=2 and loop<=1e-7,
            'min_area_ratio':min(ratios),'max_area_ratio':max(ratios),'inversions':sum(r<=0 for r in ratios),
            'max_edge_stretch':stretch,'loop_error_px':loop,
            'max_frame_displacement_px':max(math.dist(a,b) for x,y in zip(samples,samples[1:]) for a,b in zip(x[name],y[name]))}
    seams=[];names=list(setup)
    for i,a in enumerate(names):
        for b in names[i+1:]:
            pairs=[]
            for ai,p in enumerate(setup[a]):
                bi=min(range(len(setup[b])),key=lambda j:math.dist(p,setup[b][j]))
                distance=math.dist(p,setup[b][bi])
                if distance<=4:pairs.append((ai,bi,distance))
            if not pairs:continue
            growth=max(math.dist(s[a][ai],s[b][bi])-d for s in samples for ai,bi,d in pairs)
            seams.append({'regions':[a,b],'pair_count':len(pairs),'max_distance_growth_px':growth,
                          'status':'blocked' if growth>2 else 'proxy_within_tolerance'})
    return {'fps':60,'sample_count':121,'regions':rows,'seam_proxy':seams,
            'seam_coverage':'unproven','unpaired_regions':[n for n in names if not any(n in s['regions'] for s in seams)]}
