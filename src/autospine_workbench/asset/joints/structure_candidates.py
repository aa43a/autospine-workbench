"""Unselected structural layers: measured component-to-chain hypotheses only."""
from copy import deepcopy
import hashlib
from io import BytesIO
import math
import unicodedata

from ...resolved_project import canonical_sha256
from .chain_coverage import _components, MAX_PIXELS
from .layer_binding import BLOCKERS, validate_layer_bindings

PARAMETERS = {'alpha_threshold': 8, 'connectivity': 4, 'minimum_area_ratio': .01,
              'minimum_area_px': 8, 'maximum_components': 32, 'side_margin_height': .01,
              'maximum_distance_height': .15}
CHAINS = {'legwear': ('thigh', 'calf', 'foot'), 'handwear': ('upperarm', 'forearm', 'hand'),
          'footwear': ('foot',)}


def _distance(point, bone):
    a, b = bone['head_xy'], bone['tail_xy']
    delta = [b[i]-a[i] for i in (0, 1)]
    length = sum(v*v for v in delta)
    t = max(0., min(1., sum((point[i]-a[i])*delta[i] for i in (0, 1))/length)) if length else 0.
    return math.hypot(*(point[i]-a[i]-t*delta[i] for i in (0, 1)))


def assign_components(components, chains, bones, height):
    """Anatomical sides come from skeleton geometry, never canvas-left labels."""
    result = []
    for component in components:
        distances = {side: min(_distance(component['centroid'], bones[base+'_'+side])
                               for base in chains) for side in ('l', 'r')}
        nearest = min(distances, key=lambda side: (distances[side], side))
        margin = abs(distances['l']-distances['r'])/height
        side = nearest if margin >= PARAMETERS['side_margin_height'] and \
            distances[nearest]/height <= PARAMETERS['maximum_distance_height'] else None
        result.append({**deepcopy(component), 'side': side, 'distance_px': distances,
                       'margin_height': margin, 'bone_ids': [b+'_'+side for b in chains] if side else []})
    return result


def build_structure_candidates(candidate, assisted, skeleton, bindings, draft, images):
    from ...benchmark.layer_binding_draft import validate_layer_binding_draft
    from PIL import Image
    validate_layer_bindings(candidate, assisted, skeleton, bindings)
    validate_layer_binding_draft(bindings, draft)
    bones = {b['id']: b for b in skeleton['bones']}
    height = max(b['tail_xy'][1] for b in bones.values())-min(b['head_xy'][1] for b in bones.values())
    if not math.isfinite(height) or height <= 0:
        raise ValueError('structure_height_invalid')
    rows, pixels = [], 0
    for source, binding, record in zip(candidate['layers'], bindings['bindings'], draft['records']):
        if record['action'] != 'pending' or 'head_detail_name_candidate' in binding['reason_codes']:
            continue
        name = ' '.join(unicodedata.normalize('NFKC', source['name']).lower().split())
        row = {'layer_id': source['layer_id'], 'name': source['name'], 'status': 'blocked',
               'reason_code': 'semantic_ambiguous', 'proposal': None, 'components': [],
               'alpha_pixel_count': 0, 'component_count': 0, 'omitted_alpha_pixel_count': 0}
        rows.append(row)
        blocked = sorted(BLOCKERS.intersection(binding['reason_codes']))
        if blocked:
            row['reason_code'] = blocked[0]
            continue
        raw = images.get(source['layer_id'])
        if type(raw) is not bytes or len(raw) > 128*1024*1024 or hashlib.sha256(raw).hexdigest() != source['image_sha256']:
            raise ValueError('structure_image_changed')
        with Image.open(BytesIO(raw)) as image:
            x, y, r, b = source['bbox']
            pixels += image.width*image.height
            if image.format != 'PNG' or image.mode != 'RGBA' or image.size != (r-x, b-y):
                raise ValueError('structure_image_invalid')
            if pixels > MAX_PIXELS or max(image.size) > 4096:
                raise ValueError('structure_resource_limit')
            components = _components(image.getchannel('A').tobytes(), image.width, image.height, (x, y))
        total = sum(c['area'] for c in components)
        significant = [c for c in components if c['area'] >= max(8, total*.01)]
        retained = significant[:32]
        row.update(alpha_pixel_count=total, component_count=len(components), components=deepcopy(retained),
                   omitted_alpha_pixel_count=total-sum(c['area'] for c in retained))
        if not total:
            row['reason_code'] = 'empty_layer'
        elif name == 'bottomwear':
            row.update(status='needs_review', reason_code='garment_semantics_review_required',
                       proposal={'kind': 'rigid_setup_only', 'bone_ids': ['pelvis'],
                                 'secondary_motion': 'not_supported'})
        elif name in CHAINS:
            assigned = assign_components(retained, CHAINS[name], bones, height)
            row['components'] = assigned
            if len(significant) == 2 and {c['side'] for c in assigned} == {'l', 'r'}:
                row.update(status='needs_review', reason_code='component_split_review_required',
                           proposal={'kind': 'component_partition', 'bone_ids': [],
                                     'secondary_motion': 'not_supported'})
            else:
                row['reason_code'] = 'layer_requires_split' if len(significant) != 2 else 'component_side_ambiguous'
    return {'schema': 'autospine.structure-candidates/v1', 'profile': 'alpha-component-structure-v1',
            'authority': 'none', 'production_authorized': False, 'parameters': deepcopy(PARAMETERS),
            'source_bindings_sha256': canonical_sha256(bindings), 'source_draft_sha256': canonical_sha256(draft),
            'skeleton_height_px': height, 'layers': rows}


def validate_structure_candidates(candidate, assisted, skeleton, bindings, draft, images, document):
    expected = build_structure_candidates(candidate, assisted, skeleton, bindings, draft, images)
    if canonical_sha256(expected) != canonical_sha256(document):
        raise ValueError('structure_candidates_mismatch')
    return expected
