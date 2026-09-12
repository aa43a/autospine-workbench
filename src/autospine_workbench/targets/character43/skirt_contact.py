"""Source-aligned alpha contact proposals; anatomical hints never confer approval."""
from io import BytesIO
import math


def source_image(files, document, positions, slot):
    from PIL import Image
    attachment = document['skins'][0]['attachments'][slot][slot]
    path = 'images/' + attachment.get('path', slot) + '.png'
    with Image.open(BytesIO(files[path])) as loaded:
        if loaded.width*loaded.height > 4_000_000 or max(loaded.size) > 16_384:
            raise ValueError('skirt_resource_limit')
        image = loaded.convert('RGBA')
    width, height = image.size
    uv = attachment['uvs']; points = positions[slot]
    if len(uv) != 2*len(points):
        raise ValueError('skirt_source_uv_inventory')
    origins = [(p[0]-uv[2*i]*width, p[1]+uv[2*i+1]*height) for i, p in enumerate(points)]
    origin = origins[0]
    if any(math.dist(origin, p) > 1e-6 for p in origins):
        raise ValueError('skirt_source_mapping_unsupported')
    if any(abs(v-round(v)) > 1e-6 for v in origin):
        raise ValueError('skirt_source_offset_unsupported')
    return image, tuple(round(v) for v in origin)


def propose(alpha, origin, torso_images, hips):
    """Find the upper sustained torso overlap, rather than mistaking hips for a waist."""
    width, height = alpha.size
    hip_width = math.dist(*hips)
    if not math.isfinite(hip_width) or hip_width < 8:
        raise ValueError('skirt_hip_reference_invalid')
    center = tuple((a+b)/2 for a, b in zip(*hips))
    expected_y = origin[1]-center[1]
    radius = max(8, hip_width*.75)
    lower = 0
    upper = min(height-2, math.ceil(expected_y+radius))
    left = max(0, math.floor(center[0]-hip_width-origin[0]))
    right = min(width, math.ceil(center[0]+hip_width-origin[0]))
    pixels = alpha.load(); candidates = []
    for y in range(lower, upper+1):
        supported = []
        for x in range(left, right):
            if pixels[x, y] < 8:
                continue
            wx, wy = origin[0]+x, origin[1]-y
            if any(0 <= wx-o[0] < im.width and 0 <= o[1]-wy < im.height
                   and im.getpixel((wx-o[0], o[1]-wy)) >= 8 for im, o in torso_images):
                supported.append(x)
        if len(supported) >= max(3, hip_width*.25):
            candidates.append((abs(y-expected_y), -len(supported), y, supported))
    if not candidates:
        raise ValueError('skirt_waist_contact_unobservable')
    by_y = {row[2]: row[3] for row in candidates}
    sustained = [y for y in by_y if y+1 in by_y and y+2 in by_y]
    if not sustained:
        raise ValueError('skirt_waist_contact_unobservable')
    y = min(sustained); xs = by_y[y]
    return dict(waist_y=y, overlap_pixels=len(xs), overlap_x=[min(xs), max(xs)],
                hip_hint_local_y=expected_y, search_radius_px=radius,
                profile='upper-sustained-torso-alpha-contact-v1', authority='none',
                status='needs_review', reason_code='skirt_waist_anchor_review_required')
