"""Sampled alpha-overlap anchors for fixed torso versus animated arm; not seam certification."""
import io
import math
import hashlib
from .elbow_bake import replay


def locate(point,vertices,triangles):
    x,y=point
    for index,(ia,ib,ic) in enumerate(triangles):
        a,b,c=vertices[ia],vertices[ib],vertices[ic]
        denominator=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(denominator)<1e-9:continue
        u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/denominator
        v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/denominator
        if min(u,v,1-u-v)>=-1e-9:return index,[u,v,1-u-v]
    return None


def contacts(candidate,mesh,skeleton,bake,bindings,draft,images):
    # Caller validates the complete binding/bake closure; this analysis checks source pixels.
    from PIL import Image
    originals={r['layer_id']:r for r in candidate['layers']}
    options={r['layer_id']:r for r in bindings['bindings']}
    bones={b['id']:b for b in skeleton['bones']};layers={r['layer_id']:r for r in mesh['layers']}
    torsos=[]
    for r in draft['records']:
        if r['action']=='bind':
            option=next(o for o in options[r['layer_id']]['options'] if o['id']==r['option_id'])
            if option['mode']=='rigid' and option['bone_ids']==['chest']:torsos.append(r['layer_id'])
    alpha={}
    for name in torsos+[r['layer_id'] for r in bake['layers'] if r['status']=='passed']:
        if hashlib.sha256(images[name]).hexdigest()!=originals[name]['image_sha256']:raise ValueError('character_contact_image_mismatch')
        with Image.open(io.BytesIO(images[name])) as image:alpha[name]=image.convert('RGBA').getchannel('A')
    pairs=[]
    for baked in bake['layers']:
        if baked['status']!='passed':continue
        name=baked['layer_id'];row=layers[name]
        chain=[bones[w['bone_id']] for w in row['weights'][0]]
        center=chain[0]['head_xy'];radius=min(64,max(8,math.dist(chain[0]['head_xy'],chain[0]['tail_xy'])*.25))
        for torso in torsos:
            a,b=originals[name]['bbox'],originals[torso]['bbox']
            points=[]
            for y in range(math.ceil(max(a[1],b[1],center[1]-radius)),math.floor(min(a[3],b[3],center[1]+radius))):
                for x in range(math.ceil(max(a[0],b[0],center[0]-radius)),math.floor(min(a[2],b[2],center[0]+radius))):
                    if alpha[name].getpixel((x-a[0],y-a[1]))>=8 and alpha[torso].getpixel((x-b[0],y-b[1]))>=8:
                        points.append([x+.5,y+.5])
            points.sort(key=lambda p:(math.dist(p,center),p[1],p[0]))
            anchors=[]
            for point in points:
                found=locate(point,row['vertices_xy'],row['triangles'])
                if found:anchors.append({'setup_xy':point,'triangle_index':found[0],'barycentric':found[1]})
                if len(anchors)==16:break
            gap=0.
            for frame in baked['frames'] if anchors else []:
                moved=replay(row,chain,frame,frame,0)
                for anchor in anchors:
                    tri=row['triangles'][anchor['triangle_index']]
                    point=[sum(moved[i][axis]*w for i,w in zip(tri,anchor['barycentric'])) for axis in (0,1)]
                    gap=max(gap,math.dist(point,anchor['setup_xy']))
            pairs.append({'arm_layer':name,'torso_layer':torso,'overlap_pixel_count':len(points),
                          'status':'candidate_requires_review' if anchors else 'unobservable',
                          'reason_code':'sampled_alpha_overlap_only' if anchors else 'shoulder_overlap_unobservable',
                          'max_anchor_gap_px':gap if anchors else None,'anchors':anchors})
    return {'profile':'shoulder-alpha-overlap-16-v1','authority':'none','seam_certified':False,
            'sample_count_per_pair':61,'pairs':pairs}
