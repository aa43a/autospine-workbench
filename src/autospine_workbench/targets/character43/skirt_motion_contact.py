"""Track identical setup material points; separation is not a raster crack verdict."""
from hashlib import sha256
import json
import math

from .affine_pose import sample
from .deformation_qa import inspect
from .numeric_reference import read
from .skirt_contact import source_image


def locate(points, triangles, point):
    for start in range(0, len(triangles), 3):
        indices = triangles[start:start+3]
        a, b, c = [points[i] for i in indices]
        det = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(det) < 1e-10: continue
        u = ((b[1]-c[1])*(point[0]-c[0])+(c[0]-b[0])*(point[1]-c[1]))/det
        v = ((c[1]-a[1])*(point[0]-c[0])+(a[0]-c[0])*(point[1]-c[1]))/det
        weights = [u, v, 1-u-v]
        if min(weights) >= -1e-8:
            return indices, weights
    raise ValueError('skirt_contact_point_uncovered')


def transport(points, anchor):
    indices, weights = anchor
    return [sum(points[i][axis]*w for i, w in zip(indices, weights)) for axis in (0, 1)]


def analyze(files):
    inspect(files)
    document = json.loads(files['skeleton.json'])
    trial = json.loads(files['skirt-trial.json'])
    ledger = json.loads(files['character-manifest.json'])['layers']
    positions, _ = sample(dict(document, animations={'setup': {}}), 'setup', 0)
    attachments = document['skins'][0]['attachments']
    torso = []
    for layer in ledger:
        if layer['name'] in ('topwear', 'topwear-front') and layer['state'] == 'rigid_reviewed':
            for region in layer['regions']:
                slot = region['region_id']
                image, origin = source_image(files, document, positions, slot)
                torso.append((slot, image.getchannel('A'), origin))
    reference = read(files); rows = []
    for row in trial['rows']:
        slot = row['layer_id']; ox, oy = row['origin']
        image, _ = source_image(files, document, positions, slot)
        alpha = image.getchannel('A'); y = row['contact']['waist_y']
        left, right = row['contact']['overlap_x']
        anchors = []
        # Bounded, evenly spaced material samples. Retain unsupported samples explicitly.
        for x in sorted({round(left+(right-left)*i/16) for i in range(17)}):
            point = [ox+x+.5, oy-y-.5]
            if alpha.getpixel((x, y)) < 8: continue
            for other, mask, origin in torso:
                tx, ty = math.floor(point[0]-origin[0]), math.floor(origin[1]-point[1])
                if 0 <= tx < mask.width and 0 <= ty < mask.height and mask.getpixel((tx, ty)) >= 8:
                    anchors.append(dict(point=point, torso=other,
                        skirt_anchor=locate(positions[slot], attachments[slot][slot]['triangles'], point),
                        torso_anchor=locate(positions[other], attachments[other][other]['triangles'], point)))
        motions = []
        for name, frames in sorted(reference['animations'].items()):
            peak = None
            for index, frame in enumerate(frames):
                for anchor in anchors:
                    skirt = transport(frame['vertices'][slot], anchor['skirt_anchor'])
                    shirt = transport(frame['vertices'][anchor['torso']], anchor['torso_anchor'])
                    distance = math.dist(skirt, shirt)
                    if peak is None or distance > peak['separation_px']:
                        peak = dict(separation_px=distance, index=index, time=frame['time'],
                            setup_point=anchor['point'], skirt_point=skirt, torso_point=shirt,
                            torso_slot=anchor['torso'])
            motions.append(dict(animation=name, frames=len(frames), peak=peak))
        rows.append(dict(layer_id=slot, paired_samples=len(anchors), motions=motions,
            status='needs_review' if anchors else 'unobservable',
            reason_code='skirt_dynamic_contact_review_required' if anchors else 'skirt_waist_contact_unobservable'))
    return dict(schema='autospine.skirt-motion-contact/v1', authority='none',
        skeleton_sha256=sha256(files['skeleton.json']).hexdigest(), rows=rows,
        method='same_setup_alpha_supported_material_points',
        scope='numeric_reference_samples_only', raster_crack_status='not_evaluated')
