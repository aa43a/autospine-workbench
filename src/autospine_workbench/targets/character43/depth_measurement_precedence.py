"""Recognize exact regional remeasurements without removing historical evidence."""
from collections import defaultdict


def completed(check):
    count = check.get('overlap_pixels')
    if type(count) is not int or count < 0:
        return False
    status = check.get('status')
    if status == 'no_overlap':
        return count == 0 and not any(check.get('counts', {}).values())
    if status not in ('uniform_front_proxy', 'uniform_back_proxy', 'requires_partition_or_more_depth'):
        return False
    counts = check.get('counts', {})
    return (count > 0 and set(counts) == {'front', 'back', 'ambiguous', 'unknown'}
            and all(type(counts.get(k)) is int and counts[k] >= 0
            for k in ('front', 'back', 'ambiguous', 'unknown'))
            and sum(counts.values()) == count)


def superseded(depth):
    """Only suppress legacy unmeasured rows with matching completed refinement.

    Different pairs/times, unknown statuses and inconsistent duplicate evidence
    cannot supersede a measurement. Actual ordering failures are never removed.
    """
    if depth.get('profile') != 'external-regional-depth-order-v1':
        return set()
    checks = defaultdict(list)
    for row in depth.get('regional', {}).get('refinement', {}).get('rows', []):
        pair = row.get('pair')
        if not pair or len(pair) != 2:
            continue
        for check in row.get('checks', []):
            if check.get('pair') and sorted(check['pair']) != sorted(pair):
                checks[tuple(sorted(pair)), check.get('time')].append({})
            else:
                checks[tuple(sorted(pair)), check.get('time')].append(check)
    result = set()
    for pair in depth.get('pairs', []):
        names = tuple(sorted((pair['arm_slot'], pair['torso_slot'])))
        for sample in pair.get('samples', []):
            key = names, sample['tick']/1e6
            evidence = checks.get(key, [])
            signatures = [(c.get('status'), c.get('overlap_pixels'), c.get('counts')) for c in evidence]
            if (sample.get('overlap', {}).get('status') == 'unmeasured' and evidence
                    and all(completed(c) for c in evidence)
                    and all(s == signatures[0] for s in signatures)):
                result.add(key)
    return result
