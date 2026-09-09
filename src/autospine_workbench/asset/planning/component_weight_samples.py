"""Source-bound ownership checks and sampled weights, never a triangulated mesh."""
import math
from .component_ownership import template, validate as validate_draft
from .component_suggestions import ALIASES
from ..joints.mesh_weights import weights_for_vertices
from ...resolved_project import canonical_sha256

PROFILE = 'component-chain-weight-samples-v1'
SAMPLE_LIMIT = 64
PROJECT_SAMPLE_LIMIT = 256
CHAINS = {'body.arm': ['upperarm', 'forearm', 'hand'],
          'wear.sleeve': ['upperarm', 'forearm', 'hand'],
          'body.leg': ['thigh', 'calf', 'foot'],
          'wear.pants': ['thigh', 'calf', 'foot'], 'body.foot': ['foot']}


def _check(row, layer, bones):
    if row['component_id'] == 'low-alpha-residual':
        return 'residual_stays_unassigned', []
    if row['status'] == 'pending':
        return 'ownership_review_required', []
    role, side = row['semantic'], row['side']
    name = layer['name'].lower().strip()
    named_side = 'left' if name.endswith('-l') else 'right' if name.endswith('-r') else None
    source_role = layer.get('semantic') or ALIASES.get(name[:-2] if named_side else name)
    # A conflict needs explicit semantic review; never rewrite an uploaded assignment.
    if source_role and source_role != role:
        return 'source_semantic_conflict', []
    if role not in CHAINS:
        return 'garment_or_accessory_solver_required', []
    if side not in ('left', 'right') or named_side and side != named_side:
        return 'side_conflict', []
    ids = [b + ('_l' if side == 'left' else '_r') for b in CHAINS[role]]
    if set(ids) != set(row['bone_ids']):
        return 'semantic_chain_mismatch', []
    chain = [bones[b] for b in ids]
    for index, bone in enumerate(chain):
        points = bone.get('head_xy', []) + bone.get('tail_xy', [])
        angle = bone.get('world_rotation_degrees')
        if (len(points) != 4 or any(type(v) not in (int, float) or not math.isfinite(v)
                                   or abs(v) > 1e6 for v in points)
                or type(angle) not in (int, float) or not math.isfinite(angle)
                or abs(angle) > 1e6):
            return 'nonfinite_or_invalid_bone', []
        if math.dist(bone['head_xy'], bone['tail_xy']) < 1e-7:
            return 'degenerate_bone', []
        if index and bone.get('parent_id') != ids[index-1]:
            return 'disconnected_bone_chain', []
    return None, chain


def _samples(region, bbox, limit):
    count = sum(end-x for _, x, end in region['runs'])
    size = min(count, limit)
    indices = [(i * (count-1)) // max(1, size-1) for i in range(size)]
    points, offset, cursor = [], 0, 0
    for y, x, end in region['runs']:
        while cursor < size and indices[cursor] < offset + end-x:
            points.append([bbox[0]+x+indices[cursor]-offset+.5, bbox[1]+y+.5])
            cursor += 1
        offset += end-x
    return points


def build(entries, skeleton, draft, addresses, plan_sha):
    """Entries must be revalidated pixel candidates from the current input reader."""
    expected = template(draft['project_id'], entries, addresses, plan_sha,
                        [b['id'] for b in skeleton['bones']])
    validate_draft(draft, expected)
    bones = {b['id']: b for b in skeleton['bones']}
    limit = min(SAMPLE_LIMIT, PROJECT_SAMPLE_LIMIT // max(1, sum(r['status'] == 'assigned' for r in draft['records'])))
    regions = {(layer['layer_id'], r['id']): (layer, r)
               for layer, _, candidate, _ in entries
               for r in candidate['components'] + [candidate['residual']]}
    records = []
    for assignment in draft['records']:
        layer, region = regions[assignment['layer_id'], assignment['component_id']]
        reason, chain = _check(assignment, layer, bones)
        points = [] if reason else _samples(region, layer['bbox'], limit)
        if not reason and len(points) < 3:
            reason = 'insufficient_region_samples'
            points = []
        influences = []
        if points:
            if len(chain) == 3:
                influences = weights_for_vertices(points, chain)
            else:
                bone = chain[0]
                angle = math.radians(-bone['world_rotation_degrees'])
                for x, y in points:
                    dx, dy = x-bone['head_xy'][0], y-bone['head_xy'][1]
                    influences.append([dict(bone_id=bone['id'], weight=1., local_xy=[
                        dx*math.cos(angle)-dy*math.sin(angle), dx*math.sin(angle)+dy*math.cos(angle)])])
        setup_error, sum_error = 0., 0.
        for point, weights in zip(points, influences):
            reconstructed = [0., 0.]
            for weight in weights:
                bone = bones[weight['bone_id']]
                a = math.radians(bone['world_rotation_degrees'])
                x, y = weight['local_xy']
                for axis, delta in enumerate((x*math.cos(a)-y*math.sin(a), x*math.sin(a)+y*math.cos(a))):
                    reconstructed[axis] += weight['weight']*(bone['head_xy'][axis]+delta)
            setup_error = max(setup_error, math.dist(point, reconstructed))
            sum_error = max(sum_error, abs(sum(w['weight'] for w in weights)-1))
        if not reason and (setup_error > 1e-7 or sum_error > 1e-9):
            reason = 'weight_numeric_failure'
        records.append(dict(layer_id=assignment['layer_id'], component_id=assignment['component_id'],
                            status='blocked' if reason else 'sampled_candidate',
                            reason_code=reason or 'semantic_chain_checked', bone_ids=[b['id'] for b in chain],
                            samples=[dict(canvas_xy=p, influences=w) for p, w in zip(points, influences)],
                            qa=None if not points else dict(setup_max_error=setup_error, weight_sum_max_error=sum_error)))
    return dict(schema='autospine.component-weight-samples/v1', profile=PROFILE, project_id=draft['project_id'],
                sources=draft['sources'], draft_sha256=canonical_sha256(draft), skeleton_sha256=canonical_sha256(skeleton),
                sample_limit=limit, project_sample_limit=PROJECT_SAMPLE_LIMIT,
                records=records, authority='none', production_authorized=False)


def validate(document, entries, skeleton, draft, addresses, plan_sha):
    if document != build(entries, skeleton, draft, addresses, plan_sha):
        raise ValueError('component_weight_samples_mismatch')
    return document
