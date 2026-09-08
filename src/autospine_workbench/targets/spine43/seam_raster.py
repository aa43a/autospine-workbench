"""Native-pixel CPU alpha corridor probe, distinct from Runtime certification."""
from io import BytesIO
import math
from .continuous_pose import world
from .alpha_seam import position


def texture(raw):
    import numpy as np
    from PIL import Image
    with Image.open(BytesIO(raw)) as image:return np.asarray(image.convert('RGBA').getchannel('A'),dtype=float)


def mask(attachment,vertices,alpha,rect):
    import numpy as np
    x,y,w,h=rect;out=np.zeros((h,w),dtype=float);uvs=np.asarray(attachment['uvs']).reshape(-1,2)
    points=np.asarray([[p[0],-p[1]] for p in vertices]);flat=attachment['triangles'];th,tw=alpha.shape
    for offset in range(0,len(flat),3):
        indices=flat[offset:offset+3];a,b,c=points[indices]
        det=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(det)<1e-12:continue
        lo=np.maximum(np.floor(np.min(points[indices],axis=0)).astype(int),[x,y]);hi=np.minimum(np.ceil(np.max(points[indices],axis=0)).astype(int),[x+w,y+h])
        if (hi<=lo).any():continue
        px,py=np.meshgrid(np.arange(lo[0],hi[0])+.5,np.arange(lo[1],hi[1])+.5)
        u=((b[1]-c[1])*(px-c[0])+(c[0]-b[0])*(py-c[1]))/det
        v=((c[1]-a[1])*(px-c[0])+(a[0]-c[0])*(py-c[1]))/det;t=1-u-v
        inside=(u>=-1e-9)&(v>=-1e-9)&(t>=-1e-9)
        uv=u[...,None]*uvs[indices[0]]+v[...,None]*uvs[indices[1]]+t[...,None]*uvs[indices[2]]
        tx=uv[...,0]*tw-.5;ty=uv[...,1]*th-.5;ix=np.floor(tx).astype(int);iy=np.floor(ty).astype(int)
        sampled=np.zeros_like(tx)
        for dx,dy in ((0,0),(1,0),(0,1),(1,1)):
            xx,yy=ix+dx,iy+dy;valid=(xx>=0)&(xx<tw)&(yy>=0)&(yy<th)
            weight=(tx-ix if dx else 1-tx+ix)*(ty-iy if dy else 1-ty+iy)
            sampled+=np.where(valid,alpha[np.clip(yy,0,th-1),np.clip(xx,0,tw-1)]*weight,0)
        view=out[lo[1]-y:hi[1]-y,lo[0]-x:hi[0]-x];np.maximum(view,np.where(inside,sampled,0),out=view)
    return out


def corridor(points,rect):
    import numpy as np
    x,y,w,h=rect;result=np.zeros((h,w),dtype=bool)
    for a,b in points:
        steps=max(1,math.ceil(math.dist(a,b)*2))
        for i in range(steps+1):
            px=math.floor(a[0]+(b[0]-a[0])*i/steps)-x;py=math.floor(-a[1]-(b[1]-a[1])*i/steps)-y
            if 0<=px<w and 0<=py<h:result[py,px]=True
    return result


def frame_probe(doc,relation,boundaries,textures,time):
    import numpy as np
    pose=world(doc,time);a,b=relation['driver'],relation['follower']
    pairs=[(position(boundaries[a]['samples'][p['driver_sample']],pose[a]),position(boundaries[b]['samples'][p['follower_sample']],pose[b])) for p in relation['pairs']]
    xs=[p[0] for pair in pairs for p in pair];ys=[-p[1] for pair in pairs for p in pair]
    left,top=math.floor(min(xs))-4,math.floor(min(ys))-4;rect=[left,top,math.ceil(max(xs))+4-left,math.ceil(max(ys))+4-top]
    if rect[2]*rect[3]>262144:raise ValueError('seam_raster_roi_too_large')
    attachments=doc['skins'][0]['attachments']
    ma=mask(attachments[a][a],pose[a],textures[a],rect)>=8;mb=mask(attachments[b][b],pose[b],textures[b],rect)>=8
    scan=corridor(pairs,rect);gap=scan&~(ma|mb);overlap=scan&ma&mb
    metrics={'time':time,'corridor_pixels':int(scan.sum()),'gap_pixels':int(gap.sum()),'overlap_pixels':int(overlap.sum()),'roi_overlap_pixels':int((ma&mb).sum())}
    rgb=np.full((*ma.shape,3),245,dtype=np.uint8);rgb[ma]=[99,175,232];rgb[mb]=[112,196,139];rgb[ma&mb]=[110,95,190];rgb[gap]=[235,65,45]
    return metrics,(rgb,rect)


def analyze(doc,files,boundary_report):
    from PIL import Image
    textures={n:texture(files['editor/images/'+n+'.png']) for n in boundary_report['boundaries']};rows=[];images={}
    for relation in boundary_report['relations']:
        frames=[];worst=None
        for i in range(61):
            metrics,visual=frame_probe(doc,relation,boundary_report['boundaries'],textures,i/30);frames.append(metrics)
            if worst is None or metrics['gap_pixels']>worst[0]['gap_pixels']:worst=(metrics,visual)
        name=relation['driver']+'--'+relation['follower'];buffer=BytesIO();Image.fromarray(worst[1][0]).save(buffer,format='PNG');images[name+'.png']=buffer.getvalue()
        rows.append({'driver':relation['driver'],'follower':relation['follower'],'frames':frames,
            'max_gap_pixels':max(f['gap_pixels'] for f in frames),'setup_gap_pixels':frames[0]['gap_pixels'],
            'max_overlap_pixels':max(f['overlap_pixels'] for f in frames),'worst_time':worst[0]['time'],
            'worst_rect':worst[1][1],'heatmap':name+'.png','status':'candidate_requires_review'})
    return {'profile':'native-alpha8-bilinear-corridor-v1','fps':30,'sample_count':61,'relations':rows,
        'authority':'none','coverage':'candidate_corridors_only','production_authorized':False},images
