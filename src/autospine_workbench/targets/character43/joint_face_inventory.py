"""Find independently animated facial art from actual exported layer provenance."""
import json
import math

ROLE_NAMES = {'irides': 'iris', 'iris': 'iris', 'eyewhite': 'white',
              'eyelash': 'lash', 'eyebrow': 'brow', 'mouth': 'mouth', 'nose': 'nose'}


def weighted_points(attachment, bone_index):
    """Only rigid weighted meshes can be reparented without changing body weights."""
    data = attachment.get('vertices', [])
    if (attachment.get('type') != 'mesh' or len(data) == len(attachment.get('uvs', []))
            or attachment.get('parent') or not data):
        raise ValueError('facial_attachment_requires_rigid_weighted_mesh')
    points = []
    i = 0
    while i < len(data):
        if data[i] != 1 or i+5 > len(data):
            raise ValueError('facial_attachment_multiple_weights')
        count, index, x, y, weight = data[i:i+5]
        if index != bone_index or abs(weight-1) > 1e-7:
            raise ValueError('facial_attachment_parent_mismatch')
        points.append([x, y]); i += 5
    if len(points) < 3 or len(points)*2 != len(attachment.get('uvs', [])):
        raise ValueError('facial_attachment_vertex_mismatch')
    return points


def local_frame(attachment, points):
    uv = attachment['uvs']
    # Source-art x axis, independent of the head bone's setup rotation.
    first = min(range(len(points)), key=lambda i: (uv[2*i+1], uv[2*i]))
    last = max(range(len(points)), key=lambda i: (-(abs(uv[2*i+1]-uv[2*first+1])), uv[2*i]))
    dx, dy = [points[last][k]-points[first][k] for k in (0, 1)]
    if math.hypot(dx, dy) < 1e-8:
        raise ValueError('facial_attachment_frame_degenerate')
    return math.degrees(math.atan2(dy, dx))


def inventory(files, document):
    layers = []
    raw = files.get('character-manifest.json')
    if raw:
        manifest = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
        layers = manifest.get('layers', [])
    names = {row['layer_id']: row.get('name', '') for row in layers}
    bone_indices = {b['name']: i for i, b in enumerate(document['bones'])}
    parts = []
    for slot in document['slots']:
        name = names.get(slot['name'], slot['name']).lower().strip()
        token = name.replace('_', '-').replace(' ', '-')
        root = token.rsplit('-', 1)[0] if token.endswith(('-l', '-r')) else token
        role = ROLE_NAMES.get(root)
        if not role:
            continue
        side = token[-1] if token.endswith(('-l', '-r')) else 'center'
        row = dict(slot=slot['name'], name=name, role=role, side=side,
                   parent=slot['bone'], available=False, reason=None)
        try:
            motions = list(document.get('animations', {}).values())
            if any(a.get('slots', {}).get(slot['name'], {}).get('attachment') for a in motions):
                raise ValueError('facial_existing_attachment_timeline_requires_mapping')
            if any(a.get('deform', {}).get('default', {}).get(slot['name']) for a in motions):
                raise ValueError('facial_legacy_deform_requires_mapping')
            if len(document.get('skins', [])) != 1:
                raise ValueError('facial_multiple_skins_unsupported')
            choices = document['skins'][0]['attachments'][slot['name']]
            if set(choices) != {slot['attachment']}:
                raise ValueError('facial_existing_variants_require_mapping')
            mesh = choices[slot['attachment']]
            points = weighted_points(mesh, bone_indices[slot['bone']])
            frame = local_frame(mesh, points)
            row.update(available=True, attachment=slot['attachment'],
                       anchor=[sum(p[k] for p in points)/len(points) for k in (0, 1)],
                       rotation=frame, width=float(mesh.get('width', 1)),
                       height=float(mesh.get('height', 1)), vertex_count=len(points))
            row['alpha_control_available'] = not any(set(a.get('slots', {}).get(slot['name'], {})) &
                {'alpha', 'rgba', 'rgba2', 'color', 'twoColor'} for a in motions)
            row['template_available'] = role == 'mouth' and row['alpha_control_available']
            row['control_limitations'] = [] if row['alpha_control_available'] else ['existing_alpha_preserved_requires_composition']
        except (ValueError, KeyError) as error:
            row['reason'] = str(error)
        parts.append(row)
    enabled = [p for p in parts if p['available']]
    eyes = {}
    for side in ('l', 'r'):
        group = {p['role']: p for p in enabled if p['side'] == side}
        complete = all(role in group for role in ('iris', 'white', 'lash'))
        same_parent = len({p['parent'] for p in group.values() if p['role'] in ('iris', 'white', 'lash')}) == 1
        alpha_available = all(group.get(role, {}).get('alpha_control_available', False) for role in ('iris', 'white'))
        eyes[side] = dict(blink_available=complete and same_parent and alpha_available,
                          gaze_available=all(role in group for role in ('iris', 'white')) and same_parent,
                          reason=(None if complete and same_parent and alpha_available else
                                  'existing_eye_alpha_requires_composition' if complete and same_parent else
                                  'independent_white_iris_lash_required'))
    capabilities = dict(blink=any(e['blink_available'] for e in eyes.values()),
                        gaze=any(e['gaze_available'] for e in eyes.values()),
                        brows=any(p['role'] == 'brow' for p in enabled),
                        mouth=any(p['role'] == 'mouth' for p in enabled), turn=bool(enabled))
    return dict(schema='autospine.joint-face-inventory/v1', parts=parts, eyes=eyes,
                capabilities=capabilities,
                mouth_template_available=any(p.get('template_available') for p in enabled),
                missing=[name for name, available in capabilities.items() if not available],
                material_gaps=['authored_closed_eye_variant_not_mapped',
                               'authored_alternate_mouth_state_not_mapped'],
                effect_kinds=dict(blink='source_lash_compression_and_eye_group_visibility',
                                  gaze='bounded_original_iris_offset', brows='original_brow_pose',
                                  mouth='original_mouth_shape_scale', turn='limited_feature_offset'),
                material_provenance='original_texture_parameterization_no_new_expression_art',
                limitations=['blink_uses_source_lash_squash_not_drawn_closed_eye_variant',
                             'mouth_is_source_art_parameterization_not_phoneme_or_new_open_mouth_art',
                             'turn_is_limited_feature_shift_not_side_view_reconstruction'])
