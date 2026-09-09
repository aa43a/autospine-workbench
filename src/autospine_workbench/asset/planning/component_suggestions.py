"""Conservative semantic and per-component bone-sample suggestions."""
import math
from ...resolved_project import canonical_sha256

PROFILE = 'semantic-component-bone-samples-v1'
ALIASES = {'handwear': 'body.arm', 'legwear': 'body.leg', 'footwear': 'body.foot'}
SEMANTICS = {'body.arm', 'body.leg', 'body.foot', 'wear.sleeve', 'wear.pants'}
FAMILIES = {'body.arm': {'upperarm', 'forearm', 'hand'}, 'wear.sleeve': {'upperarm', 'forearm', 'hand'},
            'body.leg': {'thigh', 'calf', 'foot'}, 'wear.pants': {'thigh', 'calf', 'foot'}, 'body.foot': {'foot'}}


def build(entries, skeleton, bindings, sources):
    bones = {b['id']: b for b in skeleton['bones']}
    options = {r['layer_id']: r['options'] for r in bindings['bindings']}
    rows = []
    for layer, _, candidate, _ in entries:
        name = layer['name'].lower().strip()
        named_side = 'left' if name.endswith('-l') else 'right' if name.endswith('-r') else None
        base = name[:-2] if named_side else name
        semantic = layer.get('semantic') or ALIASES.get(base)
        for region in candidate['components'] + [candidate['residual']]:
            row = dict(layer_id=layer['layer_id'], component_id=region['id'], status='blocked',
                       reason_code='semantic_or_geometry_ambiguous', proposal=None, evidence=[])
            rows.append(row)
            if region['id'] == 'low-alpha-residual':
                row['reason_code'] = 'residual_stays_unassigned'; continue
            if semantic not in SEMANTICS:
                continue
            runs = {}
            for y, x, end in region['runs']:
                runs.setdefault(y, []).append((x, end))
            hits = {}
            for bone_id, bone in bones.items():
                if not all(math.isfinite(n) for n in bone['head_xy'] + bone['tail_xy']):
                    raise ValueError('component_suggestion_nonfinite_bone')
                count = 0
                for tick in range(21):
                    x, y = [math.floor(a+(b-a)*tick/20)-layer['bbox'][axis]
                            for axis, (a, b) in enumerate(zip(bone['head_xy'], bone['tail_xy']))]
                    count += any(start <= x < end for start, end in runs.get(y, []))
                hits[bone_id] = count
            choices = {}
            for option in options[layer['layer_id']]:
                for side, suffix in [('left', '_l'), ('right', '_r')]:
                    ids = tuple(b for b in option['bone_ids'] if b.endswith(suffix))
                    if not ids or len(ids) > 4 or named_side and side != named_side:
                        continue
                    if any(b[:-2] not in FAMILIES[semantic] for b in ids):
                        continue
                    if any(b not in bones or hits.get(b, 0) == 0 for b in ids):
                        continue
                    score = sum(hits[b] for b in ids)/(21*len(ids))
                    choices[(side, ids)] = score
            ranked = sorted(choices.items(), key=lambda r: (-r[1], r[0]))
            row['evidence'] = [dict(side=k[0], bone_ids=list(k[1]), coverage=score) for k, score in ranked]
            if not ranked or ranked[0][1] < .35 or len(ranked) > 1 and ranked[0][1]-ranked[1][1] < .15:
                continue
            (side, ids), score = ranked[0]
            row.update(status='suggested', reason_code='semantic_and_unique_component_support',
                       proposal=dict(status='assigned', semantic=semantic, side=side, bone_ids=list(ids)))
    return dict(schema='autospine.component-ownership-suggestions/v1', profile=PROFILE,
                sources= sources, skeleton_sha256=canonical_sha256(skeleton), bindings_sha256=canonical_sha256(bindings),
                parameters=dict(samples_per_bone=21, minimum_coverage=.35, minimum_margin=.15),
                records=rows, authority='none', production_authorized=False)
