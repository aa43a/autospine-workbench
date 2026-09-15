"""Source-preserving skirt mesh trial in a complete Spine character candidate."""
from copy import deepcopy
from hashlib import sha256
import json
import math

from ...automation.storage_io import canonical_bytes
from ...manifest_artifacts import require_sha256
from ...asset.planning.skirt_mesh import build_skirt_mesh
from .affine_pose import sample, matrices
from .skirt_contact import source_image, propose
from .numeric_reference import read, write
from .deformation_qa import inspect


def inverse(matrix, point):
    a, b, c, d, x, y = matrix
    determinant = a*d-b*c
    if abs(determinant) < 1e-10:
        raise ValueError('skirt_parent_transform_degenerate')
    dx, dy = point[0]-x, point[1]-y
    return [(d*dx-b*dy)/determinant, (-c*dx+a*dy)/determinant]


def generate(files, source_digest, layer_ids, *, step=32, waist_driver=None, dress_components=False):
    if waist_driver not in (None, 'reviewed-chest-v1', 'candidate-chest-v1'):
        raise ValueError('skirt_waist_driver_invalid')
    if (waist_driver=='candidate-chest-v1') != dress_components:
        raise ValueError('skirt_dress_profile_invalid')
    require_sha256(source_digest, 'Character source')
    inspect(files)  # Verify original source identity, finite samples, and complete slot inventory.
    document = json.loads(files['skeleton.json'])
    manifest = json.loads(files['character-manifest.json'])
    if document['skeleton']['spine'] != '4.3.26' or manifest.get('authority') != 'none':
        raise ValueError('skirt_character_source_unsupported')
    if not layer_ids or len(set(layer_ids)) != len(layer_ids):
        raise ValueError('skirt_layer_selection_invalid')
    ledger = {row['layer_id']: row for row in manifest['layers']}
    region_ledger={r['region_id']:l for l in ledger.values() for r in l['regions'] if r.get('state',l['state'])=='static_reference'}
    if dress_components:
        if any(i not in region_ledger or region_ledger[i]['name'] not in ('topwear','topwear-front') for i in layer_ids):
            raise ValueError('skirt_dress_selection_unsupported')
    elif any(i not in ledger or ledger[i]['name'] not in ('bottomwear', 'bottomwear-front')
           or ledger[i]['state'] != 'static_reference' for i in layer_ids):
        raise ValueError('skirt_layer_selection_unsupported')
    for animation in document['animations'].values():
        for skin in animation.get('attachments', {}).values():
            if any(any(a.get('deform') for a in skin.get(i, {}).values()) for i in layer_ids):
                raise ValueError('skirt_existing_deform_unsupported')
    setup = dict(document, animations={'setup': {}})
    positions, pose = sample(setup, 'setup', 0)
    if not {'pelvis', 'thigh_l', 'thigh_r'} <= set(pose):
        raise ValueError('skirt_body_reference_missing')
    if dress_components and 'chest' not in pose:raise ValueError('skirt_body_reference_missing')
    torso = []
    for row in ledger.values():
        if row['name'] in ('topwear', 'topwear-front') and row['state'] == 'rigid_reviewed':
            for region in row['regions']:
                image, origin = source_image(files, document, positions, region['region_id'])
                torso.append((image.getchannel('A'), origin))
    if not torso and not dress_components:
        raise ValueError('skirt_reviewed_torso_missing')
    if waist_driver == 'reviewed-chest-v1':
        from .skirt_waist_driver import require_chest_torso
        require_chest_torso(document, ledger)
    original = deepcopy(document); rows = []; helpers = []; blocked = []
    for layer_id in sorted(layer_ids):
        try:
            image, origin = source_image(files, original, positions, layer_id)
            alpha = image.getchannel('A')
            if dress_components:
                from .dress_waist import propose as dress_proposal
                from ...asset.planning.component_mount import partition
                parts=partition(alpha.tobytes(),image.width,image.height,{'chest':[pose['chest'][0]-origin[0],origin[1]-pose['chest'][1]]})
                if len(parts['regions'])!=1:raise ValueError('skirt_dress_component_not_isolated')
                contact=dress_proposal(alpha,origin,pose)
            else:
                contact = propose(alpha, origin, torso, [pose['thigh_l'][:2], pose['thigh_r'][:2]])
            raster = list(alpha.tobytes())
            mesh = build_skirt_mesh([raster[i:i+image.width] for i in range(0, len(raster), image.width)],
                                   contact['waist_y'], step)
        except ValueError as exc:
            # Analysis has not changed the scene yet: retain this layer exactly.
            code = str(exc)
            if not code.startswith('skirt_') or not code.replace('_', '').isalnum(): raise
            blocked.append(dict(layer_id=layer_id, reason_code=code))
            continue
        contact['root_torso_support'] = []
        for chain in mesh['helper_chains']:
            x, y = chain['points'][0]
            wx, wy = origin[0]+math.floor(x), origin[1]-math.floor(y)
            contact['root_torso_support'].append(any(
                0 <= wx-o[0] < im.width and 0 <= o[1]-wy < im.height
                and im.getpixel((wx-o[0], o[1]-wy)) >= 8 for im, o in ([(alpha,origin)] if dress_components else torso)))
        to_world = lambda p: [origin[0]+p[0], origin[1]-p[1]]
        names = {'pelvis': 'chest' if waist_driver else 'pelvis'}
        for chain in mesh['helper_chains']:
            parent = 'pelvis'
            for index, suffix in enumerate(('upper', 'lower')):
                neutral_name = chain['id']+'_'+suffix
                name = layer_id+'-'+neutral_name
                if name in {b['name'] for b in document['bones']}:
                    raise ValueError('skirt_helper_name_conflict')
                current = dict(document, animations={'setup': {}})
                parent_matrix = matrices(current, 'setup', 0)[parent]
                start, end = map(to_world, chain['points'][index:index+2])
                local = inverse(parent_matrix, start); distal = inverse(parent_matrix, end)
                dx, dy = distal[0]-local[0], distal[1]-local[1]
                document['bones'].append(dict(name=name, parent=parent, x=local[0], y=local[1],
                    rotation=math.degrees(math.atan2(dy, dx)), length=math.hypot(dx, dy)))
                names[neutral_name] = name; helpers.append(name); parent = name
        transforms = matrices(dict(document, animations={'setup': {}}), 'setup', 0)
        indices = {b['name']: i for i, b in enumerate(document['bones'])}
        vertices = []
        for point, influences in zip(mesh['vertices'], mesh['influences'], strict=True):
            vertices.append(len(influences))
            for influence in influences:
                name = names[influence['bone']]
                x, y = inverse(transforms[name], to_world(point))
                vertices.extend([indices[name], x, y, influence['weight']])
        attachment = document['skins'][0]['attachments'][layer_id][layer_id]
        attachment.update(vertices=vertices, uvs=[v for uv in mesh['uvs'] for v in uv],
                          triangles=[v for t in mesh['triangles'] for v in t])
        for key in ('edges', 'hull'): attachment.pop(key, None)
        rows.append(dict(layer_id=layer_id, contact=contact, mesh=mesh, origin=list(origin),
                         source_image_sha256=sha256(files['images/'+attachment.get('path', layer_id)+'.png']).hexdigest()))
    selected_ids = {row['layer_id'] for row in rows}
    reference = read(files)
    for name, animation in document['animations'].items():
        duration = reference['animations'][name][-1]['time']
        if duration <= 0: raise ValueError('skirt_animation_duration_invalid')
        for helper in helpers:
            # This is an explicit bounded probe, not a physical cloth simulation.
            amplitude = 2 if name == 'idle' else 4
            if helper.endswith('_lower'): amplitude *= .5
            animation.setdefault('bones', {})[helper] = {'rotate': [
                dict(time=duration*i/16, value=0. if i in (0, 16) else amplitude*math.sin(2*math.pi*i/16))
                for i in range(17)]}
    actual, _ = sample(dict(document, animations={'setup': {}}), 'setup', 0)
    setup_error = 0.
    for row in rows:
        expected = [[row['origin'][0]+x, row['origin'][1]-y] for x, y in row['mesh']['vertices']]
        setup_error = max(setup_error, max(math.dist(a, b) for a, b in zip(actual[row['layer_id']], expected)))
    if setup_error > 1e-6: raise ValueError('skirt_setup_reconstruction_failed')
    output = dict(files); output['skeleton.json'] = canonical_bytes(document)
    if 'editor/skeleton.json' in output:
        editor = json.loads(output['editor/skeleton.json'])
        # Preserve editor metadata, which differs from the runtime images directory.
        editor.update({key: deepcopy(document[key]) for key in ('bones', 'slots', 'skins', 'animations')})
        output['editor/skeleton.json'] = canonical_bytes(editor)
    for name, frames in reference['animations'].items():
        for frame in frames:
            vertices, _ = sample(document, name, frame['time'])
            if any(len(vertices[slot]) != len(points) or any(math.dist(a, b) > 1e-7
                   for a, b in zip(vertices[slot], points))
                   for slot, points in frame['vertices'].items() if slot not in selected_ids):
                raise ValueError('skirt_unselected_motion_changed')
            frame['vertices'] = vertices
    reference['skeleton_sha256'] = sha256(output['skeleton.json']).hexdigest()
    output = write(output, reference)
    qa = inspect(output); output['deformation.json'] = canonical_bytes(qa)
    report = dict(schema='autospine.character-skirt-trial/v1', authority='none', selected=False,
        profile='fixed-waist-three-chain-sway-v1', source_character_sha256=source_digest,
        rows=rows, setup_error_px=setup_error, geometry_passed=qa['passed'],
        status='needs_review' if qa['passed'] and rows else 'blocked',
        waist_contact_status='needs_review', leg_occlusion_status='not_evaluated',
        motion_scope='procedural_2deg_idle_4deg_other_half_distal_not_physics',
        preserved=['source_rgba', 'atlas', 'draw_order', 'unselected_motion', 'human_decisions'])
    if blocked: report['blocked_layers'] = blocked
    if waist_driver is not None:
        report['waist_driver'] = waist_driver
        report['waist_weight_mapping'] = 'neutral_pelvis_weight_to_reviewed_chest; helpers_remain_pelvis'
    if dress_components:
        report.update(profile='isolated-dress-chest-skirt-v1',waist_weight_mapping='neutral_pelvis_weight_to_candidate_chest; helpers_remain_pelvis')
    output['skirt-trial.json'] = canonical_bytes(report)
    manifest.update(profile='whole-character-skirt-trial-v1', source_character_sha256=source_digest,
                    authority='none', production_authorized=False, full_character_animation=False,
                    status=report['status'], qa=dict(runtime_status='not_run', full_character_contact_status='not_evaluated'))
    for row in manifest['layers']:
        if dress_components:
            for region in row['regions']:
                if region['region_id'] in selected_ids:region['state']='weighted_candidate'
            if any(r['region_id'] in selected_ids for r in row['regions']):
                row['state']='weighted_candidate' if all(r['state']=='weighted_candidate' for r in row['regions']) and not row.get('missing_region_ids') else 'partial'
                row['reason_codes']=sorted(set(row.get('reason_codes',[])+['skirt_waist_anchor_review_required','skirt_motion_visual_review_required']))
        elif row['layer_id'] in selected_ids:
            row['state'] = 'weighted_candidate'
            row['regions'] = [dict(region_id=row['layer_id'], state='weighted_candidate')]
            row['reason_codes'] = ['skirt_waist_anchor_review_required', 'skirt_motion_visual_review_required']
        for failure in blocked:
            if row['layer_id'] == failure['layer_id']:
                row['reason_codes'] = sorted(set(row.get('reason_codes', [])+[failure['reason_code']]))
    manifest['files'] = {n: sha256(raw).hexdigest() for n, raw in output.items() if n != 'character-manifest.json'}
    output['character-manifest.json'] = canonical_bytes(manifest)
    return output, report
