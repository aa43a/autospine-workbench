"""Compile only overlap-supported orders without crossing unknown visible parts."""
from copy import deepcopy
from .order_conflict import first_overlap, witness

PROFILE = 'external-overlap-guarded-draw-order-v1'


def _sort(slots, edges):
    output = []
    remaining = set(slots)
    while remaining:
        next_slot = next((s for s in slots if s in remaining
                          and not any(b == s and a in remaining for a, b in edges)), None)
        if next_slot is None:
            return None
        output.append(next_slot); remaining.remove(next_slot)
    return output


def build(document, animation, depth, probe):
    slots = [s['name'] for s in document['slots']]
    indices = {s: i for i, s in enumerate(slots)}
    report = dict(profile=PROFILE, selected=False, authority='none', status='blocked',
                  reason_codes=[], failures=[], frames=[], scope='sampled_order_constraints_not_visual_acceptance')
    if document['animations'][animation].get('drawOrder'):
        report['reason_codes'] = ['existing_draw_order_preserved']
        return None, report
    by_tick = {}
    for pair in depth['pairs']:
        for sample in pair['samples']:
            by_tick.setdefault(sample['tick'], []).append((pair, sample))
    ticks = sorted(by_tick)
    if not ticks:
        report['reason_codes'] = ['depth_pairs_unavailable']
        return None, report
    previous = slots; keys = []
    for index, tick in enumerate(ticks):
        time = tick/1e6
        # Guard the held order at the next midpoint as well as the source frame.
        times = [time] + ([(tick+ticks[index+1])/2e6] if index+1 < len(ticks) else [])
        edges = set(); requests = []; evidence = {}; details = {}
        try:
            for pair, row in by_tick[tick]:
                arm, torso = pair['arm_slot'], pair['torso_slot']
                visible = first_overlap(probe, arm, torso, times)
                if not visible:
                    continue
                if row['ambiguous']:
                    details = dict(pair=[arm, torso], overlap=visible)
                    raise ValueError('visible_depth_straddle')
                front = row['current_front_slot']; back = torso if front == arm else arm
                edges.add((back, front))
                evidence[back, front] = dict(source='source_depth', overlap=visible)
                if indices[back] > indices[front]:
                    requests.append((arm, min(indices[arm], indices[torso]), max(indices[arm], indices[torso])))
            for i, a in enumerate(slots):
                for b in slots[i+1:]:
                    if (a, b) in edges or (b, a) in edges:
                        continue
                    crossing = any((a == arm and lo <= indices[b] <= hi) or
                                   (b == arm and lo <= indices[a] <= hi) for arm, lo, hi in requests)
                    overlap = first_overlap(probe, a, b, times) if crossing else None
                    if crossing and not overlap:
                        continue
                    edges.add((a, b))
                    evidence[a, b] = dict(source='visible_setup_order' if crossing else 'preserved_setup_order')
                    if overlap:
                        evidence[a, b]['overlap'] = overlap
            order = _sort(slots, edges)
            if order is None:
                details = dict(conflict=witness(slots, evidence))
                raise ValueError('visible_unmapped_order_conflict')
        except ValueError as exc:
            report['failures'].append(dict(time=time, reason_code=str(exc), **details))
            continue
        if order != previous:
            keys.append(dict(time=time, offsets=[dict(slot=s, offset=order.index(s)-i) for i, s in enumerate(slots)]))
            report['frames'].append(dict(time=time, order=order))
            previous = order
    if report['failures']:
        report['reason_codes'] = sorted({f['reason_code'] for f in report['failures']})
        return None, report
    candidate = deepcopy(document)
    if keys:
        candidate['animations'][animation]['drawOrder'] = keys
    report['status'] = 'candidate' if keys else 'no_visible_order_change'
    return candidate, report
