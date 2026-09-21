"""Explain proxy uncertainty without promoting it to observed visual failure."""


def index(depth):
    regional = depth.get('regional', {})
    rows = [(r.get('pair'), r) for r in regional.get('refinement', {}).get('rows', [])]
    for section, other in [('cloth_constraints', 'cloth'), ('limb_constraints', 'leg')]:
        for pair in (regional.get(section) or {}).get('pairs', []):
            rows.extend(([pair['arm'], pair[other]], r) for r in pair['rows'])
    result = {}
    for pair, row in rows:
        if not pair or len(pair) != 2:
            continue
        for check in row.get('checks', []):
            counts = check.get('counts', {})
            if not all(type(counts.get(k)) is int and counts[k] >= 0
                       for k in ('front', 'back', 'ambiguous', 'unknown')):
                continue
            reason = ('missing_depth_support' if counts['unknown'] else
                      'opposing_model_support' if counts['front'] and counts['back'] else
                      'interval_margin_uncertain' if counts['ambiguous'] else
                      'uniform_model_support')
            key = (tuple(sorted(pair)), check['time'])
            value = dict(kind=reason, counts=dict(counts), time=check['time'],
                         scope='model_evidence_not_observed_visual_error')
            if key in result and result[key] != value:
                result[key] = dict(kind='inconsistent_model_evidence', time=check['time'])
            else:
                result[key] = value
    return result


def lookup(evidence, failure):
    pair = failure.get('pair')
    if not pair:
        return None
    time = (failure.get('overlap') or {}).get('time', failure['time'])
    return evidence.get((tuple(sorted(pair)), time))
