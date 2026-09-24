"""Order-only mesh-region candidates; never reinterpret a region's bone weights."""
from .depth_region_partition import build as partition

PROFILE = 'selected-region-static-order-v1'


def build(document, source_slot, triangles, reference_slot, side, *, part_limit=128,
          animation=None, interval=None):
    """Move selected triangles before/after a reference for the entire animation.

    This explicit editing operation is not automatic depth inference. Source and
    selected runs retain their internal order, but their mutual order may change.
    The caller must review overlap, material boundaries and all affected frames.
    """
    names = [slot['name'] for slot in document['slots']]
    if (source_slot not in names or reference_slot not in names
            or source_slot == reference_slot):
        raise ValueError('region_order_slots_invalid')
    if side not in ('before', 'after'):
        raise ValueError('region_order_side_invalid')
    slot = document['slots'][names.index(source_slot)]
    mesh = document['skins'][0]['attachments'][source_slot][slot['attachment']]
    count = len(mesh.get('triangles', [])) // 3
    if (not isinstance(triangles, (list, tuple)) or not triangles
            or any(type(t) is not int or not 0 <= t < count for t in triangles)
            or len(set(triangles)) != len(triangles)):
        raise ValueError('region_order_triangles_invalid')
    selected = set(triangles)
    labels = ['selected' if t in selected else 'retained' for t in range(count)]
    candidate, split = partition(document, [source_slot], part_limit=part_limit,
                                 triangle_labels={source_slot: labels})
    moved_names = {r['slot'] for r in split['regions'] if r['group'] == 'selected'}
    moved = [s for s in candidate['slots'] if s['name'] in moved_names]
    retained = [s for s in candidate['slots'] if s['name'] not in moved_names]
    index = next(i for i, s in enumerate(retained) if s['name'] == reference_slot)
    index += side == 'after'
    original_slots = candidate['slots']
    candidate['slots'] = retained[:index] + moved + retained[index:]
    report = dict(profile=PROFILE, authority='none', selected=False,
                  source_slot=source_slot, reference_slot=reference_slot, side=side,
                  selected_triangles=sorted(selected), regions=split['regions'],
                  scope='static_order_candidate_requires_visual_and_runtime_review',
                  weights_uv_and_deformation_preserved=True,
                  source_triangle_coverage_preserved=True,
                  triangle_order_preserved=False,
                  within_each_group_triangle_order_preserved=True)
    if interval is not None:
        from .region_order_interval import apply
        report.update(apply(candidate, original_slots, candidate['slots'], animation, interval))
    elif animation is not None:
        raise ValueError('region_order_interval_required')
    return candidate, report
