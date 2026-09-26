"""Compare the same alpha-supported waist material points on an identical time grid."""
import json
import math

from .affine_pose import sample
from .skirt_contact import source_image
from .skirt_motion_contact import locate, transport


def anchors(character, files, slot):
    if any(files.get(n) != raw for n, raw in character.items() if n.endswith('.png')):
        raise ValueError('motion_garment_contact_texture_changed')
    document = json.loads(character['skeleton.json'])
    row, = [r for r in json.loads(character['skirt-trial.json'])['rows'] if r['layer_id'] == slot]
    points = sample(dict(document, animations={'setup': {}}), 'setup', 0)[0]
    attachments = document['skins'][0]['attachments']; ox, oy = row['origin']
    alpha = source_image(character, document, points, slot)[0].getchannel('A')
    y = row['contact']['waist_y']; left, right = row['contact']['overlap_x']; torso = []
    for layer in json.loads(character['character-manifest.json'])['layers']:
        if layer['name'] in ('topwear', 'topwear-front') and layer['state'] == 'rigid_reviewed':
            for region in layer['regions']:
                other = region['region_id']; image, origin = source_image(character, document, points, other)
                torso.append((other, image.getchannel('A'), origin))
    result = []
    for x in sorted({round(left+(right-left)*i/16) for i in range(17)}):
        point = [ox+x+.5, oy-y-.5]
        if alpha.getpixel((x, y)) < 8: continue
        for other, mask, origin in torso:
            tx, ty = math.floor(point[0]-origin[0]), math.floor(origin[1]-point[1])
            if 0 <= tx < mask.width and 0 <= ty < mask.height and mask.getpixel((tx, ty)) >= 8:
                result.append(dict(torso=other,
                    skirt_anchor=locate(points[slot], attachments[slot][slot]['triangles'], point),
                    torso_anchor=locate(points[other], attachments[other][other]['triangles'], point)))
    if not result: raise ValueError('motion_garment_contact_unobservable')
    return result


def measure(frames, slot, pairs):
    peak = dict(separation_px=0., time=0.)
    for frame in frames:
        for pair in pairs:
            points = frame['vertices']
            gap = math.dist(transport(points[slot], pair['skirt_anchor']),
                            transport(points[pair['torso']], pair['torso_anchor']))
            if gap > peak['separation_px']: peak = dict(separation_px=gap, time=frame['time'])
    return peak
