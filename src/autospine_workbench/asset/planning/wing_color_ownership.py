"""Transfer saved donor pixels only into unique closed alpha-contour interiors."""
from collections import deque
from PIL import Image
from .wing_edge_ownership import decode,encode


def closed_envelope(image):
    w,h=image.size;pw,ph=w+2,h+2;blocked=bytearray(pw*ph)
    for y in range(h):
        for x in range(w):blocked[(y+1)*pw+x+1]=image.getpixel((x,y))[3]>=8
    seen=bytearray(pw*ph);seen[0]=1;queue=deque([0])
    while queue:
        i=queue.popleft();x,y=i%pw,i//pw
        for j in (i-1 if x else -1,i+1 if x+1<pw else -1,i-pw if y else -1,i+pw if y+1<ph else -1):
            if j>=0 and not seen[j] and not blocked[j]:seen[j]=1;queue.append(j)
    mask=bytes(not seen[(y+1)*pw+x+1] for y in range(h) for x in range(w))
    contour=sum(blocked);interior=sum(mask)-contour
    return mask,dict(contour_pixels=contour,closed_interior_pixels=interior,eligible=interior>=16)


def transfer(donor_raw,donor_origin,parts,origins):
    if not parts or set(parts)!=set(origins):raise ValueError('wing_color_inventory')
    for origin in [donor_origin,*origins.values()]:
        if not isinstance(origin,(list,tuple)) or len(origin)!=2 or any(type(v) is not int for v in origin):raise ValueError('wing_color_origin')
    donor=decode(donor_raw);remaining=donor.copy();images={n:decode(raw) for n,raw in sorted(parts.items())}
    if donor.width*donor.height>8_000_000 or any(image.width*image.height>8_000_000 for image in images.values()):raise ValueError('wing_color_canvas_budget')
    envelopes={};rows={};transfers={}
    for name,image in images.items():
        envelope,row=closed_envelope(image);envelopes[name]=envelope;rows[name]=dict(row,transferred_pixels=0)
        transfers[name]=Image.new('RGBA',image.size)
    counts=dict(transferred=0,ambiguous=0,outside_closed_envelopes=0)
    for y in range(donor.height):
        for x in range(donor.width):
            rgba=donor.getpixel((x,y))
            if not rgba[3]:continue
            owners=[]
            for name,image in images.items():
                px=x+donor_origin[0]-origins[name][0];py=y+donor_origin[1]-origins[name][1]
                if rows[name]['eligible'] and 0<=px<image.width and 0<=py<image.height and envelopes[name][py*image.width+px]:owners.append((name,px,py))
            if len(owners)!=1:
                counts['ambiguous' if owners else 'outside_closed_envelopes']+=1;continue
            name,px,py=owners[0];transfers[name].putpixel((px,py),rgba);remaining.putpixel((x,y),(0,0,0,0))
            rows[name]['transferred_pixels']+=1;counts['transferred']+=1
    # Reverse transport must reconstruct every visible donor RGBA byte exactly.
    rebuilt=remaining.copy()
    for name,image in transfers.items():
        for y in range(image.height):
            for x in range(image.width):
                rgba=image.getpixel((x,y))
                if rgba[3]:rebuilt.putpixel((x+origins[name][0]-donor_origin[0],y+origins[name][1]-donor_origin[1]),rgba)
    a,b=donor.tobytes(),rebuilt.tobytes()
    if any(a[i+3]!=b[i+3] or (a[i+3] and a[i:i+4]!=b[i:i+4]) for i in range(0,len(a),4)):raise ValueError('wing_color_donor_reconstruction')
    combined={n:encode(Image.alpha_composite(images[n],transfers[n])) for n in images}
    report=dict(profile='unique-closed-alpha-color-transfer-v1',alpha_threshold=8,min_interior_pixels=16,
      connectivity=4,dilation_px=0,warp=False,composition='donor_over_original_outline',counts=counts,
      components=rows,donor_reconstruction_exact=True,authority='none',production_authorized=False)
    return combined,{n:encode(image) for n,image in transfers.items()},encode(remaining),report
