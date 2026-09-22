"""Native-pixel setup comparison against source RGBA, without deleting faint pixels."""
from io import BytesIO
import math
import re


def compare_setup(document, reference, files, framebuffer, viewport):
    """Compare full source rectangles with actual setup framebuffer in PMA space.

    Restricted to normal-blend axis-aligned setup meshes; reject other mappings,
    rather than compare an incorrectly transformed CPU reference. Pillow/NumPy
    are optional analysis dependencies, never required by the compiler core.
    """
    import numpy as np
    from PIL import Image

    width, height = viewport['width'], viewport['height']
    left, top = viewport['left'], viewport['bottom'] + height
    if any(type(v) is not int for v in (width, height, left, top)) or not 0 < width <= 4096 or not 0 < height <= 4096:
        raise ValueError('character_setup_viewport')
    with Image.open(BytesIO(framebuffer)) as image:
        if image.size != (width, height):
            raise ValueError('character_setup_frame_size')
        actual = np.asarray(image.convert('RGBA'), dtype=np.float64)
    canvas = Image.new('RGBA', (width, height)); records = []
    for slot in document['slots']:
        if slot.get('blend','normal')=='normal' and re.fullmatch(r'[0-9a-fA-F]{6}00',slot.get('color','ffffffff')):
            continue  # Exact zero setup alpha contributes no source pixels.
        if slot.get('blend', 'normal') != 'normal' or slot.get('color', 'ffffffff') != 'ffffffff':
            raise ValueError('character_setup_blend_unsupported')
        mesh = document['skins'][0]['attachments'][slot['name']][slot['attachment']]
        if mesh.get('type') != 'mesh' or mesh.get('color', 'ffffffff') != 'ffffffff':
            raise ValueError('character_setup_attachment_unsupported')
        path = 'images/' + mesh.get('path', slot['attachment']) + '.png'
        with Image.open(BytesIO(files[path])) as image:
            texture = image.convert('RGBA')
        w, h = texture.size; points = reference['vertices'][slot['name']]; uv = mesh['uvs']
        if len(points)*2 != len(uv) or not points:
            raise ValueError('character_setup_vertex_inventory')
        origins = [(x - uv[2*i]*w, y + uv[2*i+1]*h) for i, (x,y) in enumerate(points)]
        x, y = origins[0]
        error = max(math.dist((x,y), point) for point in origins)
        if not math.isfinite(error) or error > 1e-5 or abs(x-round(x)) > 1e-5 or abs(y-round(y)) > 1e-5:
            raise ValueError('character_setup_source_transform_unsupported')
        offset = (round(x)-left, top-round(y))
        if offset[0]<0 or offset[1]<0 or offset[0]+w>width or offset[1]+h>height:
            raise ValueError('character_setup_texture_outside_viewport')
        hist = texture.getchannel('A').histogram()
        records.append(dict(slot_id=slot['name'], image=path, offset=list(offset),
                            faint_source_pixels=sum(hist[1:8]), visible_source_pixels=sum(hist[8:])))
        canvas.alpha_composite(texture, offset)
    expected = np.asarray(canvas, dtype=np.float64)
    # Straight RGB is unconstrained when alpha is close to zero. Compare PMA RGB
    # to prevent magnifying quantization of low-alpha pixels into visual failures.
    def pma(value):
        return np.concatenate((value[:,:,:3] * value[:,:,3:4] / 255, value[:,:,3:4]), axis=2)
    delta = np.abs(pma(actual)-pma(expected)); peak = delta.max(axis=2)
    actual_alpha = actual[:,:,3]; expected_alpha = expected[:,:,3]
    report = dict(schema='autospine.character-setup-raster/v1', authority='none', production_authorized=False,
                  scope='normal_blend_axis_aligned_setup_source_rectangles',
                  max_pma_channel_error=float(delta.max()), mean_pma_channel_error=float(delta.mean()),
                  pixels_error_over_2=int((peak>2).sum()),
                  unexpected_visible_pixels=int(((actual_alpha>=8)&(expected_alpha<8)).sum()),
                  missing_visible_pixels=int(((actual_alpha<8)&(expected_alpha>=8)).sum()),
                  faint_framebuffer_pixels=int(((actual_alpha>0)&(actual_alpha<8)).sum()),
                  faint_source_composite_pixels=int(((expected_alpha>0)&(expected_alpha<8)).sum()),
                  records=records, status='needs_review')
    output = BytesIO(); canvas.save(output, format='PNG')
    return report, output.getvalue()
