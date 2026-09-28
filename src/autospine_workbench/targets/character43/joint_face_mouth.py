"""Optional generated mouth interior, packaged as an isolated weighted mesh."""
from hashlib import sha256
from base64 import b64decode
import json

from .joint_face_config import values
from .joint_face_mouth_asset import SVG, PNG, TEMPLATE_ID


def _ordered_names(names, offsets):
    if not offsets:
        return list(names)
    order, unchanged = [None]*len(names), []
    original = 0
    for row in offsets:
        if row['slot'] not in names:
            raise ValueError('joint_face_draw_order_slot')
        at = names.index(row['slot'])
        if at < original:
            raise ValueError('joint_face_draw_order_sorted')
        while original < at:
            unchanged.append(original); original += 1
        target = original + row['offset']
        if not 0 <= target < len(order) or order[target] is not None:
            raise ValueError('joint_face_draw_order_invalid')
        order[target] = original; original += 1
    unchanged.extend(range(original, len(names)))
    for i in range(len(order)-1, -1, -1):
        if order[i] is None:
            order[i] = unchanged.pop()
    return [names[i] for i in order]


def _insert_order(document, old_names, source, added):
    new_names = list(old_names)
    new_names.insert(new_names.index(source)+1, added)
    for motion in document['animations'].values():
        if motion.get('draworder'):
            raise ValueError('joint_face_legacy_draw_order')
        for key in motion.get('drawOrder', []):
            names = _ordered_names(old_names, key.get('offsets', []))
            names.insert(names.index(source)+1, added)
            key['offsets'] = [dict(slot=name, offset=names.index(name)-i) for i, name in enumerate(new_names)]


def add_template(files, document, animation, config, part, helper, times):
    image = config['mouth'].get('template_image')
    png = b64decode(image['png_base64']) if image else PNG
    digest = sha256(png).hexdigest()
    template_id = 'user-mouth-template-'+digest if image else TEMPLATE_ID
    provenance = ('user_provided_template' if image
                  else 'code_authored_svg_rendered_once_with_napi_canvas_0.1.100')
    source = part['slot']
    name = 'm5-mouth-template-' + source
    if name in {s['name'] for s in document['slots']}:
        raise ValueError('joint_face_template_exists')
    slots = document['animations'][animation].setdefault('slots', {})
    if set(slots.get(source, {})) & {'alpha', 'rgba', 'rgba2', 'color', 'twoColor'}:
        raise ValueError('joint_face_mouth_alpha_requires_composition')
    bone = 'm5-face-template-' + source
    index = len(document['bones'])
    document['bones'].append(dict(name=bone, parent=helper, x=0., y=0., rotation=0., length=0.))
    old_names = [s['name'] for s in document['slots']]
    _insert_order(document, old_names, source, name)
    at = old_names.index(source)+1
    document['slots'].insert(at, dict(name=name, bone=bone, attachment=name, color='ffffff00'))
    # A moderate oval is independent of the source line's often tiny alpha bbox.
    width = max(4., part['width']*.92)
    height = max(3., part['width']*.62)
    points = [(-width/2, height/2), (width/2, height/2), (width/2, -height/2), (-width/2, -height/2)]
    mesh = dict(type='mesh', path=name, width=64, height=48,
                vertices=[v for x, y in points for v in (1, index, x, y, 1.)],
                triangles=[0, 1, 2, 0, 2, 3], uvs=[0, 0, 1, 0, 1, 1, 0, 1], hull=4)
    document['skins'][0]['attachments'][name] = {name: mesh}
    original_slot = next(s for s in document['slots'] if s['name'] == source)
    setup_alpha = int(original_slot.get('color', 'ffffffff')[-2:], 16)/255
    slot_alpha, source_alpha, scale, translate = [], [], [], []
    for time in times:
        opening = values(config['mouth'], time, ('open', 'wide'))['open']
        opacity = min(1., opening*2)
        slot_alpha.append(dict(time=time, value=opacity*setup_alpha))
        source_alpha.append(dict(time=time, value=(1-opacity)*setup_alpha))
        scale.append(dict(time=time, x=1., y=.12+.88*opening))
        translate.append(dict(time=time, x=0., y=-height*.08*opening))
    slots[name] = dict(alpha=slot_alpha)
    slots.setdefault(source, {})['alpha'] = source_alpha
    document['animations'][animation].setdefault('bones', {})[bone] = dict(scale=scale, translate=translate)
    atlas = files['skeleton.atlas'].decode()
    atlas += (f'\ntextures/{name}.png\nsize: 64,48\nfilter: Linear,Linear\npma: false\nrepeat: none\n'
              f'{name}\nbounds: 0,0,64,48\n\n')
    asset = dict(template_id=template_id, png_sha256=digest, width=64, height=48,
                 provenance=provenance, source_format='image/png' if image else 'image/svg+xml')
    if not image:
        asset['source'] = SVG
    updates = {'skeleton.atlas': atlas.encode(), f'textures/{name}.png': png,
               f'images/{name}.png': png, f'editor/images/{name}.png': png,
               f'generated/{name}.json': json.dumps(asset, sort_keys=True).encode()}
    report = dict(slot=name, role='mouth', template_id=template_id, parent_slot=source,
                  helper=bone, min_scale_x=1., min_scale_y=min(k['y'] for k in scale),
                  max_scale_x=1., max_scale_y=max(k['y'] for k in scale),
                  source=provenance, png_sha256=digest,
                  source_art_modified=False, generated_template=not bool(image),
                  user_provided_template=bool(image), original_art_variant=False,
                  phoneme_synchronized=False, visual_status='requires_review',
                  draw_order='adjacent_after_source_preserves_existing_relative_order')
    if not image:
        report['svg_sha256'] = sha256(SVG.encode()).hexdigest()
    return updates, report
