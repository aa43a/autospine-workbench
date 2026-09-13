"""Read exact setup shoulder contact without inferring human ownership."""
import json
import math

from .affine_pose import sample
from .skirt_contact import source_image


def contexts(files):
    document = json.loads(files['skeleton.json'])
    manifest = json.loads(files['character-manifest.json'])
    if document['skeleton']['spine'] != '4.3.26' or manifest['authority'] != 'none':
        raise ValueError('shoulder_source_unsupported')
    points, pose = sample(dict(document, animations={'setup': {}}), 'setup', 0)
    torso = []
    for layer in manifest['layers']:
        if layer['name'] not in ('topwear', 'topwear-front') or layer['state'] != 'rigid_reviewed': continue
        for region in layer['regions']:
            slot = region['region_id']; flat = document['skins'][0]['attachments'][slot][slot]['vertices']
            cursor = 0
            while cursor < len(flat):
                count = flat[cursor]; cursor += 1
                if type(count) is not int or count < 1: raise ValueError('shoulder_source_weights_invalid')
                for _ in range(count):
                    index, _, _, weight = flat[cursor:cursor+4]; cursor += 4
                    if weight > 0 and document['bones'][index]['name'] != 'chest':
                        raise ValueError('shoulder_torso_parent_unsupported')
            im, origin = source_image(files, document, points, slot)
            torso.append((im.getchannel('A'), origin))
    if not torso: raise ValueError('shoulder_reviewed_torso_missing')
    rows = []
    for layer in manifest['layers']:
        if layer['name'] not in ('handwear-l', 'handwear-r'): continue
        side = layer['name'][-1]; root = pose['upperarm_'+side][:2]; distal = pose['forearm_'+side][:2]
        length = math.dist(root, distal)
        if not math.isfinite(length) or length <= 0: raise ValueError('shoulder_length_invalid')
        for region in layer['regions']:
            slot = region['region_id']; image, origin = source_image(files, document, points, slot)
            alpha = image.getchannel('A'); contact = []
            for y in range(image.height):
                for x in range(image.width):
                    p = (origin[0]+x, origin[1]-y)
                    if math.dist(p, root) > length*.65 or alpha.getpixel((x, y)) < 8: continue
                    if any(0 <= p[0]-o[0] < a.width and 0 <= o[1]-p[1] < a.height
                           and a.getpixel((p[0]-o[0], o[1]-p[1])) >= 8 for a, o in torso): contact.append(p)
            flat = document['skins'][0]['attachments'][slot][slot]['triangles']
            rows.append(dict(slot=slot, root=root, distal=distal, contact=contact,
                             points=points[slot], triangles=[flat[i:i+3] for i in range(0, len(flat), 3)]))
    return document, rows
