"""Compile ownership into isolated tiles on one page; no geometry changes."""
from copy import deepcopy
from io import BytesIO
import hashlib
import math
from ...png_rgba import decode_rgba_png
from .partition_pixels import png

GUTTER=2


def layout(width,height):
    if any(type(v) is not int or v<1 for v in (width,height)):
        raise ValueError('ownership_atlas_dimensions_invalid')
    choices=[]
    for columns in (1,2,3):
        rows=math.ceil(3/columns);w=columns*(width+2*GUTTER);h=rows*(height+2*GUTTER)
        if w<=4096 and h<=4096 and w*h<=8*1024*1024:
            choices.append((w*h,max(w,h),columns,w,h))
    if not choices:raise ValueError('ownership_atlas_resource_limit')
    _,_,columns,w,h=min(choices)
    return w,h,[(i%columns*(width+4)+2,i//columns*(height+4)+2) for i in range(3)]


def build(source,ownership,layer):
    from PIL import Image
    image=decode_rgba_png(source);width,height=image.width,image.height
    if hashlib.sha256(image.pixels).hexdigest()!=layer['qa']['source_rgba_sha256']:
        raise ValueError('ownership_atlas_source_changed')
    with Image.open(BytesIO(ownership)) as mask:
        if mask.mode!='L' or mask.size!=(width,height):raise ValueError('ownership_atlas_mask_invalid')
        owners=mask.tobytes()
    if set(owners)-{1,2,3}:raise ValueError('ownership_atlas_owner_invalid')
    page_w,page_h,origins=layout(width,height);page=bytearray(page_w*page_h*4)
    for i,code in enumerate(owners):
        ox,oy=origins[code-1];dest=((oy+i//width)*page_w+ox+i%width)*4
        page[dest:dest+4]=image.pixels[i*4:i*4+4]
    # Exhaustively compare every tile texel to the masked source, including hidden RGB.
    restored=bytearray(len(image.pixels));tiles=[]
    for code,(ox,oy) in enumerate(origins,1):
        for y in range(height):
            for x in range(width):
                i=y*width+x;dest=((oy+y)*page_w+ox+x)*4;actual=page[dest:dest+4]
                expected=image.pixels[i*4:i*4+4] if owners[i]==code else bytes(4)
                if actual!=expected:raise ValueError('ownership_atlas_tile_mismatch')
                if owners[i]==code:restored[i*4:i*4+4]=actual
        # Linear level-0 filtering reaches at most one texel outside a tile.
        # Verify the entire two-pixel ring is zero, not just its alpha channel.
        for y in range(oy-GUTTER,oy+height+GUTTER):
            for x in range(ox-GUTTER,ox+width+GUTTER):
                if ox<=x<ox+width and oy<=y<oy+height:continue
                if any(page[(y*page_w+x)*4:(y*page_w+x)*4+4]):raise ValueError('ownership_atlas_gutter_dirty')
        tiles.append({'owner_code':code,'rect':[ox,oy,width,height],'gutter_px':GUTTER})
    if restored!=image.pixels:raise ValueError('ownership_atlas_reconstruction_failed')
    parts=[]
    for original in layer['partitions']:
        part=deepcopy(original);code=part['owner_code'];ox,oy=origins[code-1]
        uvs=part['geometry']['uvs']
        if any(len(uv)!=2 or any(not math.isfinite(v) or not 0<=v<=1 for v in uv) for uv in uvs):
            raise ValueError('ownership_atlas_uv_invalid')
        mapped=[[(ox+u*width)/page_w,(oy+v*height)/page_h] for u,v in uvs]
        error=max((math.dist([u*width,v*height],[p[0]*page_w-ox,p[1]*page_h-oy]) for (u,v),p in zip(uvs,mapped)),default=0.)
        if error>1e-7:raise ValueError('ownership_atlas_uv_mismatch')
        part['geometry']['source_uvs']=uvs;part['geometry']['uvs']=mapped
        part.update(texture_ref=layer['layer_id']+'/page.png',uv_space='normalized_page',tile_owner_code=code)
        part.pop('ownership_ref')
        parts.append(part)
    result={'layer_id':layer['layer_id'],'page_ref':layer['layer_id']+'/page.png','page_size':[page_w,page_h],
        'tiles':tiles,'partitions':parts,'residual':deepcopy(layer['residual']),
        'sampler':{'filter':'linear','mipmaps':False,'wrap':'clamp_to_edge'},
        'qa':{'rgba_reconstruction_exact':True,'tiles_exact':True,'transparent_gutters_exact':True,
              'foreign_owner_texels':0,'uv_domain_contained':True},
        'target_gate':{'status':'blocked','reason_code':'ownership_atlas_adapter_not_integrated'}}
    return result,png('RGBA',(page_w,page_h),page)
