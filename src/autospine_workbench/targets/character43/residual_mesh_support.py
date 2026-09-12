"""Diagnose residual pixel support in exact setup geometry, without adoption."""
from hashlib import sha256
from io import BytesIO
import json
import math
from .affine_pose import sample


def inside(p,a,b,c):
    ax,ay=b[0]-a[0],b[1]-a[1];bx,by=c[0]-a[0],c[1]-a[1]
    determinant=ax*by-ay*bx
    if abs(determinant)<1e-12:return False
    x,y=p[0]-a[0],p[1]-a[1]
    u=(x*by-y*bx)/determinant;v=(ax*y-ay*x)/determinant
    return u>=-1e-9 and v>=-1e-9 and u+v<=1+1e-9


def inspect(files):
    from PIL import Image
    doc=json.loads(files['skeleton.json']);manifest=json.loads(files['character-manifest.json'])
    animation=next(iter(doc['animations']))
    # Strip animation channels: support means bind/setup geometry, not first-frame motion.
    setup_doc=dict(doc,animations={animation:{}})
    positions,_=sample(setup_doc,animation,0)
    attachments=doc['skins'][0]['attachments'];rows=[]
    for layer in manifest['layers']:
        meshes=[r['region_id'] for r in layer['regions'] if r['state']=='weighted_candidate']
        if not meshes:continue
        for region in layer['regions']:
            if region['state']!='static_reference':continue
            name=region['region_id'];attachment=attachments[name][name]
            if attachment['uvs']!=[0,0,1,0,1,1,0,1] or len(positions[name])!=4:
                raise ValueError('residual_support_quad_required')
            corners=positions[name];origin=corners[0]
            ux,uy=[corners[1][k]-origin[k] for k in (0,1)]
            vx,vy=[corners[3][k]-origin[k] for k in (0,1)]
            if abs(ux*vy-uy*vx)<1e-10:raise ValueError('residual_support_degenerate')
            if math.dist(corners[2],[origin[0]+ux+vx,origin[1]+uy+vy])>1e-6:
                raise ValueError('residual_support_nonaffine_quad')
            source='images/'+attachment.get('path',name)+'.png';raw=files[source]
            with Image.open(BytesIO(raw)) as image:
                rgba=image.convert('RGBA');width,height=rgba.size;alphas=rgba.getchannel('A').tobytes()
            triangles={}
            for mesh in meshes:
                flat=attachments[mesh][mesh]['triangles'];points=positions[mesh]
                triangles[mesh]=[[points[i] for i in flat[j:j+3]] for j in range(0,len(flat),3)]
            records=[];counts={'unique_mesh_support':0,'ambiguous_mesh_support':0,'outside_mesh':0}
            for index,alpha in enumerate(alphas):
                if not alpha:continue
                x,y=index%width,index//width;u,v=(x+.5)/width,(y+.5)/height
                p=[origin[0]+u*ux+v*vx,origin[1]+u*uy+v*vy]
                owners=[mesh for mesh,ts in triangles.items() if any(inside(p,*t) for t in ts)]
                state='unique_mesh_support' if len(owners)==1 else 'ambiguous_mesh_support' if owners else 'outside_mesh'
                counts[state]+=1
                records.append(dict(pixel_xy=[x,y],alpha=alpha,state=state,mesh_regions=owners))
            rows.append(dict(layer_id=layer['layer_id'],region_id=name,source_sha256=sha256(raw).hexdigest(),
                             image_size=[width,height],counts=counts,records=records))
    return dict(schema='autospine.residual-mesh-support/v1',authority='none',selected=False,
                skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
                manifest_sha256=sha256(files['character-manifest.json']).hexdigest(),rows=rows,
                limitation='pixel_center_setup_geometry_only_not_ownership_texture_transfer_or_motion_validation')
