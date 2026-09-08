"""Disjoint preview textures preserve every source RGBA pixel at setup."""
from io import BytesIO
from PIL import Image
from ..asset.planning.mount_contact import mask
from ..asset.planning.wing_root import components


def partition(layer,raw,reported):
    groups=components(mask(layer,raw))
    if len(groups)!=len(reported) or any(len(g)!=r['area_pixels'] or i!=r['component_id']
        for i,(g,r) in enumerate(zip(groups,reported))):raise ValueError('wing_preview_components_changed')
    with Image.open(BytesIO(raw)) as image:source=image.convert('RGBA')
    residual=source.copy();x,y,_,_=layer['bbox'];parts={}
    for group,row in zip(groups,reported):
        if not row['roots']:continue
        part=Image.new('RGBA',source.size)
        for px,py in group:
            local=(px-x,py-y);part.putpixel(local,source.getpixel(local));residual.putpixel(local,(0,0,0,0))
        parts[row['component_id']]=part
    rebuilt=residual.copy()
    for part in parts.values():rebuilt=Image.alpha_composite(rebuilt,part)
    # Transparent RGB is not visible; preserve alpha and all nontransparent colors exactly.
    original=source.tobytes();restored=rebuilt.tobytes()
    for i in range(0,len(original),4):
        if original[i+3]!=restored[i+3] or (original[i+3] and original[i:i+4]!=restored[i:i+4]):
            raise ValueError('wing_preview_setup_mismatch')
    def png(image):
        out=BytesIO();image.save(out,format='PNG');return out.getvalue()
    return {key:png(value) for key,value in parts.items()},png(residual)
