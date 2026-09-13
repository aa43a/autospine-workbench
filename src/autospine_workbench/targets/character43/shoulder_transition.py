"""Experimental source-contact parent blend; never grants adoption authority."""
from copy import deepcopy
from hashlib import sha256
import json
import math

from ...automation.storage_io import canonical_bytes
from .affine_pose import sample, matrices
from .skirt_contact import source_image
from .skirt_candidate import inverse
from .numeric_reference import read, write
from .deformation_qa import inspect


def append_parent(document, slot, mixes, points, parent):
    """Append influences and remap sparse deform offsets, including zero-weight entries."""
    attachment = document['skins'][0]['attachments'][slot][slot]
    flat = attachment['vertices']; cursor = 0; vertices = []; counts = []
    matrix = matrices(dict(document, animations={'setup': {}}), 'setup', 0)[parent]
    parent_index = next(i for i, b in enumerate(document['bones']) if b['name'] == parent)
    for mix, point in zip(mixes, points, strict=True):
        if not math.isfinite(mix) or not 0 <= mix <= 1:
            raise ValueError('shoulder_mix_invalid')
        count = flat[cursor]; cursor += 1
        if type(count) is not int or count < 1:
            raise ValueError('shoulder_weighted_mesh_required')
        counts.append(count); vertices.append(count + (mix > 0))
        for _ in range(count):
            bone, x, y, weight = flat[cursor:cursor+4]; cursor += 4
            vertices.extend([bone, x, y, weight*(1-mix)])
        if mix > 0:
            x, y = inverse(matrix, point)
            vertices.extend([parent_index, x, y, mix])
    if cursor != len(flat): raise ValueError('shoulder_vertex_inventory')
    for animation in document['animations'].values():
        for skin in animation.get('attachments', {}).values():
            for choice in skin.get(slot, {}).values():
                for key in choice.get('deform', []):
                    old = [0.]*(2*sum(counts)); offset = key.get('offset', 0)
                    values = key.get('vertices', [])
                    if type(offset) is not int or offset < 0 or offset+len(values) > len(old):
                        raise ValueError('shoulder_deform_inventory')
                    old[offset:offset+len(values)] = values
                    new = []; start = 0
                    for count, mix in zip(counts, mixes, strict=True):
                        new.extend(old[start:start+2*count]); start += 2*count
                        if mix > 0: new.extend([0., 0.])
                    key.pop('offset', None); key['vertices'] = new
    attachment['vertices'] = vertices


def generate(files, source_digest):
    inspect(files)
    original = json.loads(files['skeleton.json']); document = deepcopy(original)
    manifest = json.loads(files['character-manifest.json'])
    if original['skeleton']['spine'] != '4.3.26': raise ValueError('shoulder_version_unsupported')
    setup = dict(original, animations={'setup': {}})
    positions, pose = sample(setup, 'setup', 0)
    bones = {b['name']: b for b in original['bones']}
    torso = []
    for row in manifest['layers']:
        if row['name'] not in ('topwear', 'topwear-front') or row['state'] != 'rigid_reviewed': continue
        for region in row['regions']:
            slot = region['region_id']
            # The selected parent must actually drive the reviewed torso.
            attachment = original['skins'][0]['attachments'][slot][slot]
            flat = attachment['vertices']; cursor = 0
            while cursor < len(flat):
                count = flat[cursor]; cursor += 1
                for _ in range(count):
                    index, _, _, weight = flat[cursor:cursor+4]; cursor += 4
                    if weight > 0 and original['bones'][index]['name'] != 'chest':
                        raise ValueError('shoulder_torso_parent_unsupported')
            im, origin = source_image(files, original, positions, slot)
            torso.append((im.getchannel('A'), origin))
    if not torso: raise ValueError('shoulder_reviewed_torso_missing')
    rows = []; selected = set()
    for row in manifest['layers']:
        if row['name'] not in ('handwear-l', 'handwear-r'): continue
        bone = 'upperarm_'+row['name'][-1]; root = pose[bone][:2]; length = bones[bone]['length']
        if not math.isfinite(length) or length <= 0: raise ValueError('shoulder_length_invalid')
        for region in row['regions']:
            slot = region['region_id']; image, origin = source_image(files, original, positions, slot)
            alpha = image.getchannel('A'); contact = []
            for y in range(image.height):
                for x in range(image.width):
                    p = (origin[0]+x, origin[1]-y)
                    if math.dist(p, root) > length*.65 or alpha.getpixel((x, y)) < 8: continue
                    if any(0 <= p[0]-o[0] < a.width and 0 <= o[1]-p[1] < a.height
                           and a.getpixel((p[0]-o[0], o[1]-p[1])) >= 8 for a, o in torso): contact.append(p)
            if not contact: continue
            mixes = []
            for point in positions[slot]:
                distance = min(math.dist(point, p) for p in contact)
                t = max(0., min(1., 1-distance/(length*.35)))
                mixes.append(t*t*(3-2*t))
            append_parent(document, slot, mixes, positions[slot], 'chest'); selected.add(slot)
            rows.append(dict(slot=slot, contact_pixels=len(contact), changed_vertices=sum(m > 0 for m in mixes)))
    if not selected: raise ValueError('shoulder_contact_missing')
    actual, _ = sample(dict(document, animations={'setup': {}}), 'setup', 0)
    error = max(math.dist(a, b) for slot in positions for a, b in zip(actual[slot], positions[slot], strict=True))
    if error > 1e-7: raise ValueError('shoulder_setup_changed')
    output = dict(files); output['skeleton.json'] = canonical_bytes(document)
    if 'editor/skeleton.json' in output:
        editor = json.loads(output['editor/skeleton.json'])
        editor.update({key: document[key] for key in ('bones', 'slots', 'skins', 'animations')})
        output['editor/skeleton.json'] = canonical_bytes(editor)
    reference = read(files)
    for name, frames in reference['animations'].items():
        for frame in frames:
            vertices, _ = sample(document, name, frame['time'])
            if any(math.dist(a, b) > 1e-7 for slot in vertices if slot not in selected
                   for a, b in zip(vertices[slot], frame['vertices'][slot], strict=True)):
                raise ValueError('shoulder_unselected_motion_changed')
            frame['vertices'] = vertices
    reference['skeleton_sha256'] = sha256(output['skeleton.json']).hexdigest()
    output = write(output, reference); qa = inspect(output)
    output['deformation.json'] = canonical_bytes(qa)
    report = dict(profile='source-contact-chest-blend-v1', authority='none', selected=False,
                  source_character_sha256=source_digest, rows=rows, setup_error_px=error,
                  geometry_passed=qa['passed'], runtime_status='not_run', contact_status='not_evaluated')
    output['shoulder-trial.json'] = canonical_bytes(report)
    manifest.update(profile='whole-character-shoulder-trial-v1', authority='none', production_authorized=False,
                    full_character_animation=False, status='needs_review' if qa['passed'] else 'blocked',
                    qa=dict(runtime_status='not_run', full_character_contact_status='not_evaluated'))
    manifest['files'] = {n: sha256(raw).hexdigest() for n, raw in output.items() if n != 'character-manifest.json'}
    output['character-manifest.json'] = canonical_bytes(manifest)
    return output, report
