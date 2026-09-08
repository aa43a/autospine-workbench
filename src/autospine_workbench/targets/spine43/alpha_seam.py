"""Pixel alpha boundary samples embedded in mesh UV triangles."""
from io import BytesIO
import math
from .continuous_pose import world
from .seam_translation import influences


def embed(point,uvs,triangles):
    x,y=point
    for tri in triangles:
        a,b,c=(uvs[i] for i in tri)
        det=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(det)<1e-14:continue
        u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/det
        v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/det;w=1-u-v
        if min(u,v,w)>=-1e-8:return {'triangle':tri,'barycentric':[u,v,w]}
    return None


def position(sample,vertices):
    return [sum(w*vertices[i][k] for i,w in zip(sample['triangle'],sample['barycentric'])) for k in (0,1)]


def boundary(attachment,raw):
    from PIL import Image
    with Image.open(BytesIO(raw)) as image:
        alpha=image.convert('RGBA').getchannel('A');w,h=alpha.size;pixels=alpha.tobytes()
    uvs=list(zip(attachment['uvs'][::2],attachment['uvs'][1::2]));flat=attachment['triangles']
    triangles=[flat[i:i+3] for i in range(0,len(flat),3)];samples=[];missing=0
    def visible(x,y):return 0<=x<w and 0<=y<h and pixels[y*w+x]>=8
    for y in range(h):
        for x in range(w):
            if not visible(x,y) or all(visible(x+dx,y+dy) for dx,dy in ((-1,0),(1,0),(0,-1),(0,1))):continue
            sample=embed(((x+.5)/w,(y+.5)/h),uvs,triangles)
            if sample is None:missing+=1
            else:samples.append({**sample,'pixel_xy':[x,y]})
    return {'samples':samples,'unmapped_pixels':missing,'size':[w,h]}


def nearest_pairs(left,right):
    buckets={}
    for j,p in enumerate(right):buckets.setdefault((math.floor(p[0]/4),math.floor(p[1]/4)),[]).append(j)
    pairs=[]
    for i,p in enumerate(left):
        x,y=math.floor(p[0]/4),math.floor(p[1]/4)
        eligible=[j for dx in (-1,0,1) for dy in (-1,0,1) for j in buckets.get((x+dx,y+dy),[])]
        if not eligible:continue
        j=min(eligible,key=lambda j:(math.dist(p,right[j]),j));distance=math.dist(p,right[j])
        if distance<=4:pairs.append({'driver_sample':i,'follower_sample':j,'setup_distance_px':distance})
    return pairs


def analyze(doc,files):
    setup=world(doc,0);attachments={n:s[n] for n,s in doc['skins'][0]['attachments'].items()}
    boundaries={n:boundary(a,files['editor/images/'+n+'.png']) for n,a in attachments.items()}
    positions={n:[position(s,setup[n]) for s in b['samples']] for n,b in boundaries.items()};relations=[]
    for follower,a in attachments.items():
        bones=influences(a)
        if len(bones)!=1:continue
        for driver,b in attachments.items():
            if len(influences(b))<2 or not bones.issubset(influences(b)):continue
            pairs=nearest_pairs(positions[driver],positions[follower])
            if pairs:relations.append({'driver':driver,'follower':follower,'pairs':pairs,'review_status':'pending'})
    frames=[world(doc,i/60) for i in range(121)]
    for relation in relations:
        a,b=relation['driver'],relation['follower'];growth=0.;maximum=0.
        for frame in frames:
            for pair in relation['pairs']:
                p=position(boundaries[a]['samples'][pair['driver_sample']],frame[a])
                q=position(boundaries[b]['samples'][pair['follower_sample']],frame[b]);distance=math.dist(p,q)
                maximum=max(maximum,distance);growth=max(growth,distance-pair['setup_distance_px'])
        relation.update(max_distance_px=maximum,max_distance_growth_px=growth,
                        status='blocked' if growth>2 else 'candidate_requires_review')
    return {'profile':'alpha8-pixel-center-barycentric-v1','boundaries':boundaries,'relations':relations,
            'fps':60,'sample_count':121,'authority':'none','contact_correspondence':'candidate_only',
            'unpaired_regions':[n for n in attachments if not any(n in (r['driver'],r['follower']) for r in relations)]}
