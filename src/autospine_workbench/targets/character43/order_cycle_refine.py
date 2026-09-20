"""Relax only measured-disjoint setup constraints within ordering cycles."""
from .order_conflict import witness, first_overlap

PROFILE = 'sampled-disjoint-cycle-refinement-v1'


def compact_cycle(slots, evidence):
    cycle = witness(slots, evidence)
    if cycle is None:
        return None
    path = cycle['slots'][:-1]
    # Shorten the diagnostic via existing directed chords; not a shortest-cycle claim.
    changed = True
    while changed:
        changed = False
        for i in range(len(path)):
            for distance in range(len(path)-1, 1, -1):
                rotated = path[i:] + path[:i]
                if (rotated[0], rotated[distance]) in evidence:
                    path = [rotated[0]] + rotated[distance:]
                    changed = True
                    break
            if changed:
                break
    path.append(path[0])
    return dict(slots=path, edges=[dict(back=a, front=b, **evidence[a, b])
                                  for a, b in zip(path, path[1:])])


def resolve(slots, edges, evidence, probe, times, sort, *, check_limit=128):
    audit = dict(profile=PROFILE, removed=[], checks=[], status='blocked')
    order = sort(slots, edges)
    while order is None:
        cycle = compact_cycle(slots, evidence)
        pending = [e for e in cycle['edges'] if e['source'] == 'preserved_setup_order']
        removed = False
        for edge in pending:
            if len(audit['checks']) >= check_limit:
                audit.update(reason_code='depth_cycle_check_limit', conflict=cycle)
                return None, audit
            a, b = edge['back'], edge['front']
            try:
                overlap = first_overlap(probe, a, b, times)
            except ValueError as exc:
                audit.update(reason_code=str(exc), conflict=cycle)
                return None, audit
            check = dict(back=a, front=b, times=list(times), overlap=overlap)
            audit['checks'].append(check)
            if overlap:
                evidence[a, b] = dict(source='visible_setup_order', overlap=overlap)
            else:
                edges.remove((a, b)); del evidence[a, b]
                audit['removed'].append(check)
                removed = True
                break
        if not removed:
            audit.update(reason_code='visible_unmapped_order_conflict',
                         conflict=compact_cycle(slots, evidence))
            return None, audit
        order = sort(slots, edges)
    audit['status'] = 'sampled_constraints_satisfied'
    return order, audit
