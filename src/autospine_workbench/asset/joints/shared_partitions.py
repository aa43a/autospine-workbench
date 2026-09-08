"""One source texture, disjoint ownership, and source-bound regional weights."""
from copy import deepcopy
from io import BytesIO
import hashlib
import math

from ...png_rgba import decode_rgba_png
from ...resolved_project import canonical_sha256


def combine_layer(source, ownership, metadata, rows, region_images):
    from PIL import Image
    image = decode_rgba_png(source)
    if hashlib.sha256(source).hexdigest() != metadata['source_image_sha256']:
        raise ValueError('shared_partition_source_changed')
    x,y,right,bottom = metadata['bbox']
    if (image.width,image.height) != (right-x,bottom-y):
        raise ValueError('shared_partition_dimensions_invalid')
    with Image.open(BytesIO(ownership)) as mask:
        if mask.mode != 'L' or mask.size != (image.width,image.height):
            raise ValueError('shared_partition_mask_invalid')
        owners = mask.tobytes()
    if set(owners)-{1,2,3}: raise ValueError('shared_partition_owner_invalid')
    if len(rows)!=2 or {r['side'] for r in rows}!={'l','r'}:
        raise ValueError('shared_partition_sides_invalid')
    pixels=image.pixels; rebuilt=bytearray(len(pixels));partitions=[]
    texture=metadata['layer_id']+'/source.png';mask_ref=metadata['layer_id']+'/ownership.png'
    for row in rows:
        code=1 if row['side']=='l' else 2
        expected=bytearray(len(pixels))
        for i,owner in enumerate(owners):
            if owner==code: expected[i*4:i*4+4]=pixels[i*4:i*4+4]
        raw=region_images[row['layer_id']]
        if hashlib.sha256(raw).hexdigest()!=row['image_sha256'] or decode_rgba_png(raw).pixels!=bytes(expected):
            raise ValueError('shared_partition_region_changed')
        for i,owner in enumerate(owners):
            if owner==code: rebuilt[i*4:i*4+4]=expected[i*4:i*4+4]
        if len(row['vertices_xy'])!=len(row['uvs']) or len(row['weights'])!=len(row['uvs']):
            raise ValueError('shared_partition_mesh_invalid')
        max_error=0.; zones={bone:0 for bone in row['bone_ids']};mixed=0
        for vertex,uv,weights in zip(row['vertices_xy'],row['uvs'],row['weights']):
            error=math.dist(vertex,[x+uv[0]*image.width,y+uv[1]*image.height])
            if not math.isfinite(error) or error>1e-7:raise ValueError('shared_partition_uv_mismatch')
            max_error=max(error,max_error)
            active=[w for w in weights if w['weight']>1e-9]
            if any(w['bone_id'] not in zones or not math.isfinite(w['weight']) or not 0<=w['weight']<=1 for w in weights) or abs(sum(w['weight'] for w in weights)-1)>1e-9:
                raise ValueError('shared_partition_weight_invalid')
            if len(active)==1: zones[active[0]['bone_id']]+=1
            else: mixed+=1
        partitions.append({'id':row['layer_id'],'owner_code':code,'texture_ref':texture,'ownership_ref':mask_ref,
            'source_region_mesh_sha256':canonical_sha256(row),'bone_ids':row['bone_ids'],
            'geometry':{k:deepcopy(row[k]) for k in ('vertices_xy','uvs','triangles','weights')},
            'weight_support':{'rigid_vertex_counts':zones,'transition_vertex_count':mixed,'confidence':'uncalibrated'},
            'qa':{'source_uv_max_error_px':max_error,'deformation':row['qa'],'coverage':row['raster_qa']},
            'status':row['status'],'review_status':'pending'})
    for i,owner in enumerate(owners):
        if owner==3:rebuilt[i*4:i*4+4]=pixels[i*4:i*4+4]
    if bytes(rebuilt)!=pixels:raise ValueError('shared_partition_reconstruction_failed')
    return {'layer_id':metadata['layer_id'],'bbox':metadata['bbox'],'texture_ref':texture,'ownership_ref':mask_ref,
        'partitions':partitions,'residual':{'owner_code':3,'status':'preserved_unbound',
            'visible_pixels':sum(o==3 and pixels[i*4+3]>0 for i,o in enumerate(owners)),
            'bone_ids':[],'confidence':'unresolved'},
        'qa':{'rgba_reconstruction_exact':True,'source_rgba_sha256':hashlib.sha256(pixels).hexdigest(),
              'reconstructed_rgba_sha256':hashlib.sha256(rebuilt).hexdigest()},
        'target_gate':{'status':'blocked','reason_code':'shared_texture_ownership_not_compiled'}}
