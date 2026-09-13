"""Stable slot precedence experiments; geometry and review decisions are preserved."""
from hashlib import sha256
import heapq
import json

from ...automation.storage_io import canonical_bytes
from ...resolved_project import canonical_sha256
from .numeric_reference import read, write


def stable_order(names, constraints):
    if len(set(names)) != len(names) or not names:
        raise ValueError('character_order_slot_inventory')
    if not constraints or len(constraints) > 256:
        raise ValueError('character_order_constraints')
    rank = {name: i for i, name in enumerate(names)}
    edges = set()
    for row in constraints:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise ValueError('character_order_constraint_shape')
        back, front = row
        if back not in rank or front not in rank or back == front:
            raise ValueError('character_order_slot_missing')
        edges.add((back, front))
    following = {name: set() for name in names}
    incoming = dict.fromkeys(names, 0)
    for back, front in edges:
        following[back].add(front)
        incoming[front] += 1
    ready = [rank[n] for n in names if incoming[n] == 0]
    heapq.heapify(ready)
    ordered = []
    while ready:
        name = names[heapq.heappop(ready)]
        ordered.append(name)
        for other in sorted(following[name], key=rank.get):
            incoming[other] -= 1
            if incoming[other] == 0:
                heapq.heappush(ready, rank[other])
    if len(ordered) != len(names):
        raise ValueError('character_order_cycle')
    return ordered, sorted(edges)


def generate(files, constraints):
    document = json.loads(files['skeleton.json'])
    manifest = json.loads(files['character-manifest.json'])
    if document.get('skeleton', {}).get('spine') != '4.3.26':
        raise ValueError('character_order_target')
    if manifest.get('authority') != 'none' or manifest.get('production_authorized') is not False:
        raise ValueError('character_order_authority')
    for animation in document['animations'].values():
        if 'drawOrder' in animation or 'draworder' in animation:
            raise ValueError('character_order_animated_dependency')
    for skin in document['skins']:
        for attachments in skin['attachments'].values():
            if any(a.get('type') == 'clipping' for a in attachments.values()):
                raise ValueError('character_order_clipping_dependency')
    names = [s['name'] for s in document['slots']]
    ordered, edges = stable_order(names, constraints)
    by_name = {s['name']: s for s in document['slots']}
    document['slots'] = [by_name[n] for n in ordered]
    reference = read(files)
    if reference['skeleton_sha256'] != sha256(files['skeleton.json']).hexdigest():
        raise ValueError('character_order_reference_identity')
    output = dict(files)
    output['skeleton.json'] = canonical_bytes(document)
    if 'editor/skeleton.json' in files:
        editor = json.loads(files['editor/skeleton.json'])
        if editor['slots'] != json.loads(files['skeleton.json'])['slots']:
            raise ValueError('character_order_editor_inventory')
        editor['slots'] = document['slots']
        output['editor/skeleton.json'] = canonical_bytes(editor)
    reference['skeleton_sha256'] = sha256(output['skeleton.json']).hexdigest()
    output = write(output, reference)
    report = dict(schema='autospine.character-order-candidate/v1',
                  profile='stable-slot-precedence-v1', authority='none', selected=False,
                  production_authorized=False,
                  source_bundle_sha256=canonical_sha256({n: sha256(b).hexdigest() for n, b in files.items()}),
                  constraints=[list(e) for e in edges], before=names, after=ordered,
                  changed=ordered != names, runtime_status='not_run', visual_status='needs_review',
                  preserved=['bones', 'attachments', 'weights', 'uvs', 'textures', 'animations',
                             'vertex_references', 'binding_decisions'])
    output['order-candidate.json'] = canonical_bytes(report)
    manifest.update(profile='stable-slot-precedence-v1', source_character_sha256=report['source_bundle_sha256'],
                    status='needs_review', full_character_animation=False,
                    qa={'runtime_status': 'not_run', 'draw_order_visual_status': 'needs_review'})
    manifest['files'] = {n: sha256(b).hexdigest() for n, b in output.items() if n != 'character-manifest.json'}
    output['character-manifest.json'] = canonical_bytes(manifest)
    return output, report
