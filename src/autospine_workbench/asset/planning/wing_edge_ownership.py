"""Conservative, non-growing ownership transfer of existing faint wing pixels."""
from io import BytesIO
from PIL import Image


PROFILE='wing-faint-edge-unique-owner-2px-v1'


def decode(raw):
    with Image.open(BytesIO(raw)) as image:return image.convert('RGBA')


def encode(image):
    out=BytesIO();image.save(out,format='PNG');return out.getvalue()


def refine(parts,residual,selected):
    """Transfer alpha 1..7 only when exactly one original component is within 2px."""
    if not set(selected).issubset(parts):raise ValueError('wing_edge_unknown_selection')
    images={key:decode(raw) for key,raw in sorted(parts.items())};rest=decode(residual)
    if any(image.size!=rest.size for image in images.values()):raise ValueError('wing_edge_size')
    w,h=rest.size;owners={};original=rest.copy()
    for key,image in images.items():
        for y in range(h):
            for x in range(w):
                alpha=image.getpixel((x,y))[3]
                if not alpha:continue
                if (x,y) in owners or rest.getpixel((x,y))[3]:raise ValueError('wing_edge_non_disjoint')
                if alpha<8:raise ValueError('wing_edge_requires_original_components')
                owners[x,y]=key
        original=Image.alpha_composite(original,image)
    offsets=[(dx,dy) for dy in range(-2,3) for dx in range(-2,3) if 0<dx*dx+dy*dy<=4]
    counts=dict(transferred=0,ambiguous=0,no_nearby_owner=0,unselected_owner=0,opaque_residual=0)
    changes=[]
    for y in range(h):
        for x in range(w):
            rgba=rest.getpixel((x,y));alpha=rgba[3]
            if not alpha:continue
            if alpha>=8:counts['opaque_residual']+=1;continue
            nearby={owners[x+dx,y+dy] for dx,dy in offsets if (x+dx,y+dy) in owners}
            if not nearby:counts['no_nearby_owner']+=1;continue
            if len(nearby)!=1:counts['ambiguous']+=1;continue
            key=next(iter(nearby))
            if key not in selected:counts['unselected_owner']+=1;continue
            images[key].putpixel((x,y),rgba);rest.putpixel((x,y),(0,0,0,0))
            changes.append(dict(owner=key,local_xy=[x,y],rgba=list(rgba)));counts['transferred']+=1
    rebuilt=rest.copy()
    for image in images.values():rebuilt=Image.alpha_composite(rebuilt,image)
    before,after=original.tobytes(),rebuilt.tobytes()
    for i in range(0,len(before),4):
        if before[i+3]!=after[i+3] or (before[i+3] and before[i:i+4]!=after[i:i+4]):
            raise ValueError('wing_edge_setup_changed')
    report=dict(profile=PROFILE,radius_px=2,alpha_range=[1,7],recursive_growth=False,
      counts=counts,changes=changes,setup_visible_rgba_exact=True,
      authority='none',production_authorized=False)
    return {key:encode(image) for key,image in images.items()},encode(rest),report
